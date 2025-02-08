import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import lazyload
from sqlalchemy import update
from meshtastic.protobuf.config_pb2 import Config
from meshtastic.protobuf.portnums_pb2 import PortNum
from meshtastic.protobuf.mesh_pb2 import User, HardwareModel
from meshview import database
from meshview import decode_payload
from meshview.models import Packet, PacketSeen, Node, Traceroute
from meshview import notify



async def process_envelope(topic, env):

    # Checking if the received packet is a MAP_REPORT
    # Update the node table with the firmware version
    if env.packet.decoded.portnum == PortNum.MAP_REPORT_APP:
        # Extract the node ID from the packet (renamed from 'id' to 'node_id' to avoid conflicts with Python's built-in id function)
        node_id = getattr(env.packet, "from")

        # Decode the MAP report payload to extract the firmware version
        map_report = decode_payload.decode_payload(PortNum.MAP_REPORT_APP, env.packet.decoded.payload)

        # Establish an asynchronous database session
        async with database.async_session() as session:
            # Construct an SQLAlchemy update statement
            stmt = (
                update(Node)
                .where(Node.node_id == node_id)  # Ensure correct column reference
                .values(firmware=map_report.firmware_version)  # Assign new firmware value
            )

            # Execute the update statement asynchronously
            await session.execute(stmt)

            # Commit the changes to the database
            await session.commit()

    # This ignores any packet that does not have a ID
    if not env.packet.id:
        return

    async with database.async_session() as session:
        result = await session.execute(select(Packet).where(Packet.id == env.packet.id))
        new_packet = False
        packet = result.scalar_one_or_none()
        if not packet:
            new_packet = True
            packet = Packet(
                id=env.packet.id,
                portnum=env.packet.decoded.portnum,
                from_node_id=getattr(env.packet, "from"),
                to_node_id=env.packet.to,
                payload=env.packet.SerializeToString(),
                # p.r. Here seems to be where the packet is imported on the Database and import time is set.
                import_time=datetime.datetime.now(),
                channel=env.channel_id,
            )
            session.add(packet)

        result = await session.execute(
            select(PacketSeen).where(
                PacketSeen.packet_id == env.packet.id,
                PacketSeen.node_id == int(env.gateway_id[1:], 16),
                PacketSeen.rx_time == env.packet.rx_time,
            )
        )
        seen = None
        if not result.scalar_one_or_none():
            seen = PacketSeen(
                packet_id=env.packet.id,
                node_id=int(env.gateway_id[1:], 16),
                channel=env.channel_id,
                rx_time=env.packet.rx_time,
                rx_snr=env.packet.rx_snr,
                rx_rssi=env.packet.rx_rssi,
                hop_limit=env.packet.hop_limit,
                hop_start=env.packet.hop_start,
                topic=topic,
                # p.r. Here seems to be where the packet is imported on the Database and import time is set.
                import_time=datetime.datetime.now(),
            )
            session.add(seen)



        if env.packet.decoded.portnum == PortNum.NODEINFO_APP:
            user = decode_payload.decode_payload(
                PortNum.NODEINFO_APP, env.packet.decoded.payload
            )
            if user:
                result = await session.execute(select(Node).where(Node.id == user.id))
                if user.id and user.id[0] == "!":
                    try:
                        node_id = int(user.id[1:], 16)
                    except ValueError:
                        node_id = None
                        pass
                else:
                    node_id = None

                try:
                    hw_model = HardwareModel.Name(user.hw_model)
                except ValueError:
                    hw_model = "unknown"
                try:
                   role = Config.DeviceConfig.Role.Name(user.role)
                except ValueError:
                    role = "unknown"

                if node := result.scalar_one_or_none():
                    node.node_id = node_id
                    node.long_name = user.long_name
                    node.short_name = user.short_name
                    node.hw_model = hw_model
                    node.role = role
                    node.last_update =datetime.datetime.now()

                else:
                    node = Node(
                        id=user.id,
                        node_id=node_id,
                        long_name=user.long_name,
                        short_name=user.short_name,
                        hw_model=hw_model,
                        role=role,
                        channel=env.channel_id,
                        # if need to update time of last update it may be here
                    )
                    session.add(node)

        if env.packet.decoded.portnum == PortNum.POSITION_APP:
            position = decode_payload.decode_payload(
                PortNum.POSITION_APP, env.packet.decoded.payload
            )
            if position and position.latitude_i and position.longitude_i:
                from_node_id = getattr(env.packet, 'from')
                node = (await session.execute(select(Node).where(Node.node_id == from_node_id))).scalar_one_or_none()
                if node:
                    node.last_lat = position.latitude_i
                    node.last_long = position.longitude_i
                    session.add(node)

        if env.packet.decoded.portnum == PortNum.TRACEROUTE_APP:
            packet_id = None
            if env.packet.decoded.want_response:
                packet_id = env.packet.id
            else:
                result = await session.execute(select(Packet).where(Packet.id == env.packet.decoded.request_id))
                if result.scalar_one_or_none():
                    packet_id = env.packet.decoded.request_id
            if packet_id is not None:
                session.add(Traceroute(
                    packet_id=packet_id,
                    route=env.packet.decoded.payload,
                    done=not env.packet.decoded.want_response,
                    gateway_node_id=int(env.gateway_id[1:], 16),
                    import_time=datetime.datetime.now(),
                ))

        await session.commit()
        if new_packet:
            await packet.awaitable_attrs.to_node
            await packet.awaitable_attrs.from_node
            notify.notify_packet(packet.to_node_id, packet)
            notify.notify_packet(packet.from_node_id, packet)
            notify.notify_packet(None, packet)
        if seen:
            notify.notify_uplinked(seen.node_id, packet)


async def get_node(node_id):
    async with database.async_session() as session:
        result = await session.execute(select(Node).where(Node.node_id == node_id))
        return result.scalar_one_or_none()


async def get_fuzzy_nodes(query):
    async with database.async_session() as session:
        q = select(Node).where(
            Node.id.ilike(query + "%")
            | Node.long_name.ilike(query + "%")
            | Node.short_name.ilike(query + "%")
        )
        result = await session.execute(q)
        return result.scalars()


async def get_packets(node_id=None, portnum=None, since=None, limit=500, before=None, after=None):
    async with database.async_session() as session:
        q = select(Packet)

        if node_id:
            q = q.where(
                (Packet.from_node_id == node_id) | (Packet.to_node_id == node_id)
            )
        if portnum:
            q = q.where(Packet.portnum == portnum)
        if since:
            q = q.where(Packet.import_time > (datetime.datetime.now() - since))
        if before:
            q = q.where(Packet.import_time < before)
        if after:
            q = q.where(Packet.import_time > after)
        if limit is not None:
            q = q.limit(limit)

        result = await session.execute(q.order_by(Packet.import_time.desc()))
        return result.scalars()


async def get_packets_from(node_id=None, portnum=None, since=None, limit=500):
    async with database.async_session() as session:
        q = select(Packet)

        if node_id:
            q = q.where(
                Packet.from_node_id == node_id
            )
        if portnum:
            q = q.where(Packet.portnum == portnum)
        if since:
            q = q.where(Packet.import_time > (datetime.datetime.now() - since))
        result = await session.execute(q.limit(limit).order_by(Packet.import_time.desc()))
        return result.scalars()


async def get_packet(packet_id):
    async with database.async_session() as session:
        q = select(Packet).where(Packet.id == packet_id)
        result = await session.execute(q)
        return result.scalar_one_or_none()


async def get_uplinked_packets(node_id, portnum=None):
    async with database.async_session() as session:
        q = select(Packet).join(PacketSeen).where(PacketSeen.node_id == node_id).order_by(Packet.import_time.desc()).limit(500)
        if portnum:
            q = q.where(Packet.portnum == portnum)
        result = await session.execute(q)
        return result.scalars()


async def get_packets_seen(packet_id):
    async with database.async_session() as session:
        result = await session.execute(
            select(PacketSeen)
            .where(PacketSeen.packet_id == packet_id)
            .order_by(PacketSeen.import_time.desc())
        )
        return result.scalars()


async def has_packets(node_id, portnum):
    async with database.async_session() as session:
        return bool(
            (await session.execute(
                    select(Packet.id).where(Packet.from_node_id == node_id).limit(1)
            )).scalar()
        )


async def get_traceroute(packet_id):
    async with database.async_session() as session:
        result = await session.execute(
                select(Traceroute)
                .where(Traceroute.packet_id == packet_id)
                .order_by(Traceroute.import_time)
        )
        return result.scalars()


async def get_traceroutes(since):
    async with database.async_session() as session:
        result = await session.execute(
                select(Traceroute)
                .join(Packet)
                .where(Traceroute.import_time > (datetime.datetime.now() - since))
                .order_by(Traceroute.import_time)
        )
        return result.scalars()


async def get_mqtt_neighbors(since):
    async with database.async_session() as session:
        result = await session.execute(select(PacketSeen, Packet)
            .join(Packet)
            .where(
                (PacketSeen.hop_limit == PacketSeen.hop_start)
                & (PacketSeen.hop_start != 0)
                & (PacketSeen.import_time > (datetime.datetime.now() - since))
            )
            .options(
                lazyload(Packet.from_node),
                lazyload(Packet.to_node),
            )
        )
        return result

# In order to provide separate network graphs for LongFast and MediumSlow, I am duplicating the procedures.
# 3 procedures are needed. These would have to be replicated for any other network that we may need to use graphs.
#
# get_traceroutes_longfast
# get_packets_longfast
# get_mqtt_neighbors_longfast
#
# p.r.
#
# Get Traceroute for LongFast only
async def get_traceroutes_longfast(since):
    async with database.async_session() as session:
        result = await session.execute(
                select(Traceroute)
                .join(Packet)
                .where(
                (Traceroute.import_time > (datetime.datetime.now() - since))
                & (Packet.channel == "LongFast")
                )
                .order_by(Traceroute.import_time)
        )
        return result.scalars()

# Get MQTT Neighbors for LongFast only
# p.r.
async def get_mqtt_neighbors_longfast(since):
    async with database.async_session() as session:
        result = await session.execute(select(PacketSeen, Packet)
            .join(Packet)
            .where(
                (PacketSeen.hop_limit == PacketSeen.hop_start)
                & (PacketSeen.hop_start != 0)
                & (Packet.channel == "LongFast")
            )

            .options(
                lazyload(Packet.from_node),
                lazyload(Packet.to_node),
            )
        )
        return result

# Get Packets for LongFast only
# p.r.
async def get_packets_longfast(node_id=None, portnum=None, since=None, limit=500, before=None, after=None):
    async with database.async_session() as session:
        q = select(Packet)

        # Add condition for channel being "LongFast"
        q = q.where(Packet.channel == "LongFast")

        if node_id:
            q = q.where(
                (Packet.from_node_id == node_id) | (Packet.to_node_id == node_id)
            )
        if portnum:
            q = q.where(Packet.portnum == portnum)
        if since:
            q = q.where(Packet.import_time > (datetime.datetime.now() - since))
        if before:
            q = q.where(Packet.import_time < before)
        if after:
            q = q.where(Packet.import_time > after)
        if limit is not None:
            q = q.limit(limit)

        result = await session.execute(q.order_by(Packet.import_time.desc()))
        return result.scalars()

# Get Traceroute for mediumslow only
# p.r.
async def get_traceroutes_mediumslow(since):
    async with database.async_session() as session:
        result = await session.execute(
                select(Traceroute)
                .join(Packet)
                .where(
                (Traceroute.import_time > (datetime.datetime.now() - since))
                & (Packet.channel == "MediumSlow")
                )
                .order_by(Traceroute.import_time)
        )
        return result.scalars()

# Get MQTT Neighbors for mediumslow only
# p.r.
async def get_mqtt_neighbors_mediumslow(since):
    async with database.async_session() as session:
        result = await session.execute(select(PacketSeen, Packet)
            .join(Packet)
            .where(
                (PacketSeen.hop_limit == PacketSeen.hop_start)
                & (PacketSeen.hop_start != 0)
                & (Packet.channel == "MediumSlow")
            )

            .options(
                lazyload(Packet.from_node),
                lazyload(Packet.to_node),
            )
        )
        return result

# Get Packets for MediumSlow only
# p.r.
async def get_packets_mediumslow(node_id=None, portnum=None, since=None, limit=500, before=None, after=None):
    async with database.async_session() as session:
        q = select(Packet)

        # Add condition for channel being "MediumSlow"
        q = q.where(Packet.channel == "MediumSlow")

        if node_id:
            q = q.where(
                (Packet.from_node_id == node_id) | (Packet.to_node_id == node_id)
            )
        if portnum:
            q = q.where(Packet.portnum == portnum)
        if since:
            q = q.where(Packet.import_time > (datetime.datetime.now() - since))
        if before:
            q = q.where(Packet.import_time < before)
        if after:
            q = q.where(Packet.import_time > after)
        if limit is not None:
            q = q.limit(limit)

        result = await session.execute(q.order_by(Packet.import_time.desc()))
        return result.scalars()



# We count the total amount of packages
# This is to be used by /stats in web.py
async def get_total_packet_count():
    async with database.async_session() as session:
        q = select(func.count(Packet.id))  # Use SQLAlchemy's func to count packets
        result = await session.execute(q)
        return result.scalar()  # Return the total count of packets

# We count the total amount of nodes
async def get_total_node_count():
    async with database.async_session() as session:
        q = select(func.count(Node.id))  # Use SQLAlchemy's func to count nodes
        q = q.where(Node.last_update > datetime.datetime.now() - datetime.timedelta(days=1)) # Look for nodes with nodeinfo updates in the last 24 hours
        result = await session.execute(q)
        return result.scalar()  # Return the total count of nodes

# We count the total amount of seen packets
async def get_total_packet_seen_count():
    async with database.async_session() as session:
        q = select(func.count(PacketSeen.node_id))  # Use SQLAlchemy's func to count nodes
        result = await session.execute(q)
        return result.scalar()  # Return the total count of seen packets


async def get_total_node_count_longfast() -> int:
    try:
        # Open an asynchronous session with the database
        async with database.async_session() as session:
            # Build the query to count nodes where channel == 'LongFast'
            q = select(func.count(Node.id))
            q = q.where(Node.last_update > datetime.datetime.now() - datetime.timedelta( days=1))  # Look for nodes with nodeinfo updates in the last 24 hours
            q = q.where(Node.channel == 'LongFast')  #

            # Execute the query asynchronously and fetch the result
            result = await session.execute(q)

            # Return the scalar value (the count of nodes)
            return result.scalar()
    except Exception as e:
        # Log or handle the exception if needed (optional, replace with logging if necessary)
        print(f"An error occurred: {e}")
        return 0  # Return 0 or an appropriate fallback value in case of an error


async def get_total_node_count_mediumslow() -> int:
    try:
        # Open an asynchronous session with the database
        async with database.async_session() as session:
            # Build the query to count nodes where channel == 'LongFast'
            q = select(func.count(Node.id))
            q = q.where(Node.last_update > datetime.datetime.now() - datetime.timedelta(
                days=1))  # Look for nodes with nodeinfo updates in the last 24 hours
            q = q.where(Node.channel == 'MediumSlow')  #
            # Execute the query asynchronously and fetch the result
            result = await session.execute(q)

            # Return the scalar value (the count of nodes)
            return result.scalar()
    except Exception as e:
        # Log or handle the exception if needed (optional, replace with logging if necessary)
        print(f"An error occurred: {e}")
        return 0  # Return 0 or an appropriate fallback value in case of an error


# Get Nodes for mediumslow only
# p.r.
async def get_nodes_mediumslow():
    async with database.async_session() as session:
        result = await session.execute(
                select(Node)
                .where(
                (Node.channel == "MediumSlow")
                )
        )
        return result.scalars()



async def get_nodes():
    async with database.async_session() as session:
        result = await session.execute(
                select(Node)
                .where(Node.last_update != "")
                .order_by(Node.long_name)  # Sorting by long_name
        )
        return result.scalars()





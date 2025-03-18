import datetime
from sqlalchemy import select
from sqlalchemy import update
from meshtastic.protobuf.config_pb2 import Config
from meshtastic.protobuf.portnums_pb2 import PortNum
from meshtastic.protobuf.mesh_pb2 import User, HardwareModel
from meshview import mqtt_database
from meshview import decode_payload
from meshview.models import Packet, PacketSeen, Node, Traceroute




async def process_envelope(topic, env):

    # Checking if the received packet is a MAP_REPORT
    # Update the node table with the firmware version
    if env.packet.decoded.portnum == PortNum.MAP_REPORT_APP:
        # Extract the node ID from the packet (renamed from 'id' to 'node_id' to avoid conflicts with Python's built-in id function)
        node_id = getattr(env.packet, "from")

        # Decode the MAP report payload to extract the firmware version
        map_report = decode_payload.decode_payload(PortNum.MAP_REPORT_APP, env.packet.decoded.payload)

        # Establish an asynchronous database session
        async with mqtt_database.async_session() as session:
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

    async with mqtt_database.async_session() as session:
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
                    node.channel = env.channel_id
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

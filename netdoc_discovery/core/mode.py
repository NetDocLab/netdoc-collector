#!/usr/bin/env python3
"""NetDoc discoverer."""

import os
import shutil
import argparse
import logging
import sys
import uuid
import socket
import asyncio
import json
from datetime import datetime
from pathlib import Path
import yaml
import websockets

# REPORT_PATH_FMT = '%Y%m%d-%H%M%S'

# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s  %(levelname)-8s  %(name)s  %(message)s',
#     datefmt='%Y-%m-%dT%H:%M:%S',
#     filename='netdoc_discovery.log',
# )
# logger = logging.getLogger(__name__)


# def load_config(path: str) -> dict:
#     try:
#         with open(path) as f:
#             return yaml.safe_load(f)
#     except FileNotFoundError:
#         pass
#     return {}


# # ---------------------------------------------------------------------------
# # Managed mode
# # ---------------------------------------------------------------------------

# def run_discovery(inventory: dict, report_path: Path, num_workers: int) -> list:
#     """Esegui la discovery e ritorna la lista di device scoperti."""
#     # TODO: integra qui la logica nornir esistente
#     raise NotImplementedError


async def handle_snapshot(websocket, message: dict, agent_id: str, report_path: Path, num_workers: int):
    """Esegui uno snapshot e invia il risultato al backend."""
    snapshot_id = message['snapshot_id']
    inventory = message['inventory']

    logging.info('Receiving snapshot from backend (snapshot_id=%s)', snapshot_id)

    # TODO: mark snapshot as running

    # try:
    #     devices = run_discovery(inventory, report_path, num_workers)

    #     await websocket.send(
    #         json.dumps(
    #             {
    #                 'type': 'snapshot_result',
    #                 'snapshot_id': snapshot_id,
    #                 'status': 'complete',
    #                 'devices': devices,
    #             }
    #         )
    #     )
    #     logging.info('Snapshot %s: completato (%d device)', snapshot_id, len(devices))

    # except Exception as e:
    #     logging.exception('Snapshot %s: fallito', snapshot_id)
    #     await websocket.send(
    #         json.dumps(
    #             {
    #                 'type': 'snapshot_result',
    #                 'snapshot_id': snapshot_id,
    #                 'status': 'failed',
    #                 'error': str(e),
    #             }
    #         )
    #     )


async def heartbeat_loop(websocket, agent_id: str, current_snapshot: dict):
    """Send periodic heartbeat to backend to indicate liveness and current snapshot (if any)."""
    while True:
        await asyncio.sleep(30)
        try:
            await websocket.send(
                json.dumps(
                    {
                        'type': 'heartbeat',
                        'agent_id': agent_id,
                        'snapshot_id': current_snapshot.get('id'),  # None se idle
                    }
                )
            )
        except Exception:
            break  # il loop principale gestirà la riconnessione


async def managed_mode(
    backend_url: str,
    backend_token: str,
    backend_verify: bool,
    agent_id: str,
    report_path: Path,
    num_workers: int,
):
    # convert http(s) → ws(s)
    ws_url = backend_url.replace('https://', 'wss://').replace('http://', 'ws://')
    ws_url = f"{ws_url.rstrip('/')}/ws/v1/collectors/"

    ssl_context = None
    if ws_url.startswith('wss://') and not backend_verify:
        import ssl

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    logging.info('Connecting to backend via WS (backend_url=%s, agent_id=%s)', ws_url, agent_id)

    backoff = 5  # Initial backoff in seconds for reconnection attempts

    while True:
        try:
            async with websockets.connect(
                ws_url, ssl=ssl_context, additional_headers={"Authorization": f"Bearer {backend_token}"}
            ) as websocket:
                logging.info('Connected to backend (backend_url=%s, agent_id=%s)', ws_url, agent_id)
                backoff = 5  # Reset backoff after successful connection

                current_snapshot = {}  # Track current snapshot being processed (if any)
                asyncio.create_task(heartbeat_loop(websocket, agent_id, current_snapshot))

                async for raw_message in websocket:
                    message = json.loads(raw_message)
                    msg_type = message.get('type')

                    if msg_type == 'populate_snapshot':
                        if current_snapshot.get('id'):
                            # Another agent is working on a snapshot, ignore this one (should not happen if backend is correctly locking)
                            logging.warning(
                                'Received snapshot %s but another agent is processing %s',
                                message['snapshot_id'],
                                current_snapshot['id'],
                            )
                            continue

                        current_snapshot['id'] = message['snapshot_id']
                        try:
                            await handle_snapshot(websocket, message, agent_id, report_path, num_workers)
                        finally:
                            current_snapshot.clear()  # torna idle

                    elif msg_type == 'ping':
                        await websocket.send(json.dumps({'type': 'pong'}))

                    else:
                        logging.warning('Messaggio sconosciuto: %s', msg_type)

        except websockets.exceptions.InvalidStatusCode as e:
            if e.status_code == 4401:
                logging.error('Invalid or unauthorized token. Exiting.')
                return 1
            logging.warning('Connection refused (%s), retry in %ds', e.status_code, backoff)

        except Exception as e:
            logging.warning('Connection lost (%s), retry in %ds', e, backoff)

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)  # Exponential backoff, max 60s

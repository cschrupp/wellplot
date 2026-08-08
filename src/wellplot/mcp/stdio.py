###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""Asyncio-backed stdio transport for the local MCP server."""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING

import anyio
import mcp.types as types
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.shared.message import SessionMessage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.fastmcp import FastMCP


@asynccontextmanager
async def _stdio_streams() -> AsyncIterator[
    tuple[
        MemoryObjectReceiveStream[SessionMessage | Exception],
        MemoryObjectSendStream[SessionMessage],
    ]
]:
    """Bridge process stdio to MCP memory streams without a blocking worker."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader),
        sys.stdin.buffer,
    )
    writer_transport, writer_protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin,
        sys.stdout.buffer,
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

    read_send, read_receive = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    write_send, write_receive = anyio.create_memory_object_stream[SessionMessage](0)

    async def read_input() -> None:
        async with read_send:
            while line := await reader.readline():
                try:
                    message = types.JSONRPCMessage.model_validate_json(line)
                except Exception as exc:
                    await read_send.send(exc)
                    continue
                await read_send.send(SessionMessage(message))

    async def write_output() -> None:
        async with write_receive:
            async for session_message in write_receive:
                payload = session_message.message.model_dump_json(
                    by_alias=True,
                    exclude_none=True,
                )
                writer.write((payload + "\n").encode("utf-8"))
                await writer.drain()

    try:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(read_input)
            task_group.start_soon(write_output)
            yield read_receive, write_send
            task_group.cancel_scope.cancel()
    finally:
        writer.close()
        with suppress(NotImplementedError):
            await writer.wait_closed()


async def run_stdio_async(server: FastMCP) -> None:
    """Run a FastMCP server over process stdio."""
    async with _stdio_streams() as (read_stream, write_stream):
        await server._mcp_server.run(
            read_stream,
            write_stream,
            server._mcp_server.create_initialization_options(),
        )


def run_stdio(server: FastMCP) -> None:
    """Run a FastMCP server synchronously over process stdio."""
    anyio.run(run_stdio_async, server)

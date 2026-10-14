"""MCP delegates collaboration to the same authorized REST boundary as the UI."""
from urllib.parse import quote


def install_tools(mcp, request, api_prefix='/api'):
    def path(kind, ident):
        return f'{api_prefix}/collaboration/{quote(kind, safe="")}/{quote(ident, safe="")}'

    @mcp.tool()
    async def list_collaboration_attachments(resource_kind: str, resource_id: str) -> list[dict]:
        """List scoped immutable attachment metadata, including size and SHA-256."""
        return await request('GET', path(resource_kind, resource_id) + '/attachments')

    @mcp.tool()
    async def upload_collaboration_attachment(resource_kind: str, resource_id: str, filename: str, content_base64: str, request_id: str) -> dict:
        """Upload 1 byte to 10 MiB. The API validates filename, scope, write role and idempotency."""
        return await request('POST', path(resource_kind, resource_id) + '/attachments',
            body={'filename': filename, 'content_base64': content_base64}, request_id=request_id)

    @mcp.tool()
    async def set_collaboration_subscription(resource_kind: str, resource_id: str, subscribed: bool, request_id: str) -> dict:
        """Follow or unfollow a readable resource for the authenticated principal only."""
        return await request('POST', path(resource_kind, resource_id) + '/subscription',
            body={'subscribed': subscribed}, request_id=request_id)

    @mcp.tool()
    async def list_collaboration_participants(resource_kind: str, resource_id: str) -> list[dict]:
        """List current authorized colleagues/Agents that may be mentioned on this resource."""
        return await request('GET', path(resource_kind, resource_id) + '/participants')

    @mcp.tool()
    async def read_collaboration_discussion(resource_kind: str, resource_id: str) -> list[dict]:
        """Read scoped plain-text discussion with authenticated author attribution."""
        return await request('GET', path(resource_kind, resource_id) + '/discussion')

    @mcp.tool()
    async def send_collaboration_discussion(resource_kind: str, resource_id: str, body: str, mention_ids: list[str], request_id: str) -> dict:
        """Post a discussion and optional scoped mentions atomically with notifications."""
        return await request('POST', path(resource_kind, resource_id) + '/discussion',
            body={'body': body, 'mention_ids': mention_ids}, request_id=request_id)

    @mcp.tool()
    async def read_collaboration_notifications() -> list[dict]:
        """Read this principal's notifications, rechecking current resource authorization."""
        return await request('GET', api_prefix + '/collaboration/notifications')

    @mcp.tool()
    async def mark_collaboration_notification_read(notification_id: str, request_id: str) -> dict:
        """Mark an owned, currently readable notification as read."""
        return await request('POST', f'{api_prefix}/collaboration/notifications/{quote(notification_id, safe="")}/read', request_id=request_id)

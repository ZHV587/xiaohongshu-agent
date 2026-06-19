# tools/lark_scopes.py

# A curated set of scopes needed for im, base, drive, task, and calendar domains.
LARK_SCOPES = [
    "im:message",
    "im:message.send_as_user",
    "im:chat",
    "im:chat.members:read",
    "base:form:update",
    "drive:drive",
    "drive:file:download",
    "drive:file:upload",
    "task:task:read",
    "task:task:write",
    "calendar:calendar:read",
    "calendar:calendar.event:create",
    "wiki:space:read",
    "wiki:node:read",
    "wiki:node:retrieve",
    "docx:document:readonly",
]


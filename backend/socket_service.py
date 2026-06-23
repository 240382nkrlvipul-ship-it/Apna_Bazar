from flask_socketio import SocketIO, join_room, leave_room
from flask import request

# Global SocketIO instance, initialized here to prevent circular dependencies
socketio = SocketIO(cors_allowed_origins="*")

@socketio.on('join_room')
def on_join(data):
    room = data.get('room')
    if room:
        join_room(room)
        print(f"Socket Client (SID: {request.sid}) joined room: {room}")

@socketio.on('leave_room')
def on_leave(data):
    room = data.get('room')
    if room:
        leave_room(room)
        print(f"Socket Client (SID: {request.sid}) left room: {room}")

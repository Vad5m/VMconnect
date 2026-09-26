from kivy.logger import Logger

try:
    from android.permissions import request_permissions, Permission
    ANDROID = True
except ImportError:
    ANDROID = False

    class Permission:
        INTERNET = 'android.permission.INTERNET'
        ACCESS_NETWORK_STATE = 'android.permission.ACCESS_NETWORK_STATE'
        ACCESS_WIFI_STATE = 'android.permission.ACCESS_WIFI_STATE'
        CHANGE_WIFI_STATE = 'android.permission.CHANGE_WIFI_STATE'
        CHANGE_NETWORK_STATE = 'android.permission.CHANGE_NETWORK_STATE'
        ACCESS_FINE_LOCATION = 'android.permission.ACCESS_FINE_LOCATION'
        ACCESS_COARSE_LOCATION = 'android.permission.ACCESS_COARSE_LOCATION'
        WRITE_EXTERNAL_STORAGE = 'android.permission.WRITE_EXTERNAL_STORAGE'
        READ_EXTERNAL_STORAGE = 'android.permission.READ_EXTERNAL_STORAGE'
        MANAGE_EXTERNAL_STORAGE = 'android.permission.MANAGE_EXTERNAL_STORAGE'
        CAMERA = 'android.permission.CAMERA'
        RECORD_AUDIO = 'android.permission.RECORD_AUDIO'
        READ_PHONE_STATE = 'android.permission.READ_PHONE_STATE'
        READ_PHONE_NUMBERS = 'android.permission.READ_PHONE_NUMBERS'
        CALL_PHONE = 'android.permission.CALL_PHONE'
        READ_CALL_LOG = 'android.permission.READ_CALL_LOG'
        WRITE_CALL_LOG = 'android.permission.WRITE_CALL_LOG'
        PROCESS_OUTGOING_CALLS = 'android.permission.PROCESS_OUTGOING_CALLS'
        READ_CONTACTS = 'android.permission.READ_CONTACTS'
        WRITE_CONTACTS = 'android.permission.WRITE_CONTACTS'
        GET_ACCOUNTS = 'android.permission.GET_ACCOUNTS'
        READ_CALENDAR = 'android.permission.READ_CALENDAR'
        WRITE_CALENDAR = 'android.permission.WRITE_CALENDAR'
        POST_NOTIFICATIONS = 'android.permission.POST_NOTIFICATIONS'
        BLUETOOTH_SCAN = 'android.permission.BLUETOOTH_SCAN'
        BLUETOOTH_CONNECT = 'android.permission.BLUETOOTH_CONNECT'
        BLUETOOTH_ADVERTISE = 'android.permission.BLUETOOTH_ADVERTISE'
        NEARBY_WIFI_DEVICES = 'android.permission.NEARBY_WIFI_DEVICES'
        BLUETOOTH = 'android.permission.BLUETOOTH'
        BLUETOOTH_ADMIN = 'android.permission.BLUETOOTH_ADMIN'
        WAKE_LOCK = 'android.permission.WAKE_LOCK'
        VIBRATE = 'android.permission.VIBRATE'
        RECEIVE_BOOT_COMPLETED = 'android.permission.RECEIVE_BOOT_COMPLETED'
        FOREGROUND_SERVICE = 'android.permission.FOREGROUND_SERVICE'

    def request_permissions(perms, callback=None):
        Logger.info(f'Permissions: skipped (not Android): {perms}')
        if callback:
            callback(perms, [True] * len(perms))


PERMISSIONS_TO_REQUEST = [
    Permission.INTERNET,
    Permission.ACCESS_NETWORK_STATE,
    Permission.ACCESS_WIFI_STATE,
    Permission.CHANGE_WIFI_STATE,
    Permission.CHANGE_NETWORK_STATE,
    Permission.NEARBY_WIFI_DEVICES,
    Permission.ACCESS_FINE_LOCATION,
    Permission.ACCESS_COARSE_LOCATION,
    Permission.READ_EXTERNAL_STORAGE,
    Permission.WRITE_EXTERNAL_STORAGE,
    Permission.CAMERA,
    Permission.RECORD_AUDIO,
    Permission.READ_PHONE_STATE,
    Permission.READ_PHONE_NUMBERS,
    Permission.CALL_PHONE,
    Permission.READ_CALL_LOG,
    Permission.WRITE_CALL_LOG,
    Permission.PROCESS_OUTGOING_CALLS,
    Permission.READ_CONTACTS,
    Permission.WRITE_CONTACTS,
    Permission.GET_ACCOUNTS,
    Permission.READ_CALENDAR,
    Permission.WRITE_CALENDAR,
    Permission.POST_NOTIFICATIONS,
    Permission.BLUETOOTH_SCAN,
    Permission.BLUETOOTH_CONNECT,
    Permission.BLUETOOTH_ADVERTISE,
    Permission.BLUETOOTH,
    Permission.BLUETOOTH_ADMIN,
    Permission.WAKE_LOCK,
    Permission.VIBRATE,
    Permission.RECEIVE_BOOT_COMPLETED,
    Permission.FOREGROUND_SERVICE,
]


def _on_permissions_result(permissions, grants):
    for perm, granted in zip(permissions, grants):
        status = 'OK' if granted else 'DENIED'
        Logger.info(f'Permissions: {perm} -> {status}')


def request_android_permissions():
    """Request all permissions needed by the app."""
    try:
        Logger.info('Permissions: requesting permission set...')
        request_permissions(PERMISSIONS_TO_REQUEST, _on_permissions_result)
    except Exception as e:
        Logger.error(f'request_permissions: {e}')
        raise

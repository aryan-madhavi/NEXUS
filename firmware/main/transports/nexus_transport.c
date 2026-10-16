#include "nexus_transport.h"

const char *nexus_conn_state_str(nexus_conn_state_t state)
{
    switch (state) {
    case NEXUS_CONN_STATE_DISCONNECTED: return "DISCONNECTED";
    case NEXUS_CONN_STATE_CONNECTING:   return "CONNECTING";
    case NEXUS_CONN_STATE_CONNECTED:    return "CONNECTED";
    case NEXUS_CONN_STATE_DEGRADED:     return "DEGRADED";
    case NEXUS_CONN_STATE_FAILED:       return "FAILED";
    default:                            return "UNKNOWN";
    }
}

const char *nexus_transport_type_str(nexus_transport_type_t type)
{
    switch (type) {
    case NEXUS_TRANSPORT_TYPE_SERIAL:   return "SERIAL";
    case NEXUS_TRANSPORT_TYPE_MQTT:     return "MQTT";
    default:                            return "UNKNOWN";
    }
}

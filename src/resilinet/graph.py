"""FalkorDB connection factory. Connectivity is checked by the caller."""

from falkordb import FalkorDB

from resilinet.config import Settings, get_settings


def get_graph(settings: Settings | None = None):
    """Select the configured graph using the official FalkorDB Python client."""
    config = settings or get_settings()
    client = FalkorDB(
        host=config.falkordb_host,
        port=config.falkordb_port,
        username=config.falkordb_username,
        password=config.falkordb_password,
    )
    return client.select_graph(config.falkordb_graph)


def check_graph_connection(settings: Settings | None = None) -> bool:
    """Run a harmless read query; return False when FalkorDB is unavailable."""
    try:
        graph = get_graph(settings)
        graph.ro_query("RETURN 1 AS ok")
    except Exception:
        return False
    return True

from mcp_server_travel.mcp_tools_travel.mcp.server import get_parks_nearby
from mcp_server_travel.mcp_tools_travel.services import get_activity_spots

if __name__ == "__main__":
    # {'activity': 'jogging', 'lat': 41.8933203, 'lon': 12.4829321, 'radius_km': 5}
    activities = get_activity_spots(activity='jogging', lat=41.8933203, lon=12.4829321, radius_km=5)
    for activity in activities:
        print(activity)

    spots = get_parks_nearby(52.520008, 13.404954, radius_km=5.0)
    for s in spots:
        print(s.name, s.tags["distance_km"])
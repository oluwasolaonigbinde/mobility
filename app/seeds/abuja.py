"""Local synthetic areas around real Abuja districts (longitude, latitude)."""


def district_polygon(name):
    bounds = (
        (7.47, 9.095, 7.51, 9.125)
        if "Maitama" in name
        else (7.39, 9.055, 7.44, 9.10)
        if "Jabi" in name
        else (7.49, 9.025, 7.54, 9.065)
        if "Asokoro" in name
        else (7.465, 9.015, 7.50, 9.045)
        if "Garki" in name
        else (7.44, 9.055, 7.485, 9.105)
    )
    west, south, east, north = bounds
    return {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }

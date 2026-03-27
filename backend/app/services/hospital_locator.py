from __future__ import annotations

import math

import httpx


OFFLINE_CARE_LOCATIONS = [
    {
        "name": "Jayadeva Institute of Cardiovascular Sciences",
        "kind": "Heart Specialist",
        "latitude": 12.9309,
        "longitude": 77.5962,
        "address": "Bannerghatta Main Road, Bengaluru",
    },
    {
        "name": "Apollo Hospitals Bannerghatta Road",
        "kind": "Hospital",
        "latitude": 12.8999,
        "longitude": 77.5963,
        "address": "Bannerghatta Road, Bengaluru",
    },
    {
        "name": "Manipal Hospital Old Airport Road",
        "kind": "Hospital",
        "latitude": 12.9586,
        "longitude": 77.6496,
        "address": "Old Airport Road, Bengaluru",
    },
    {
        "name": "Fortis Hospital Anandapur",
        "kind": "Hospital",
        "latitude": 22.5018,
        "longitude": 88.4007,
        "address": "Anandapur, Kolkata",
    },
    {
        "name": "BM Birla Heart Research Centre",
        "kind": "Heart Specialist",
        "latitude": 22.5408,
        "longitude": 88.3638,
        "address": "Alipore, Kolkata",
    },
    {
        "name": "AMRI Hospital Dhakuria",
        "kind": "Hospital",
        "latitude": 22.5138,
        "longitude": 88.3698,
        "address": "Dhakuria, Kolkata",
    },
    {
        "name": "All India Institute of Medical Sciences",
        "kind": "Hospital",
        "latitude": 28.5672,
        "longitude": 77.2100,
        "address": "Ansari Nagar, New Delhi",
    },
    {
        "name": "Max Super Speciality Hospital Saket",
        "kind": "Hospital",
        "latitude": 28.5277,
        "longitude": 77.2160,
        "address": "Saket, New Delhi",
    },
    {
        "name": "Fortis Escorts Heart Institute",
        "kind": "Heart Specialist",
        "latitude": 28.5604,
        "longitude": 77.2828,
        "address": "Okhla Road, New Delhi",
    },
    {
        "name": "Kokilaben Dhirubhai Ambani Hospital",
        "kind": "Hospital",
        "latitude": 19.1311,
        "longitude": 72.8254,
        "address": "Andheri West, Mumbai",
    },
    {
        "name": "Lilavati Hospital and Research Centre",
        "kind": "Hospital",
        "latitude": 19.0509,
        "longitude": 72.8296,
        "address": "Bandra West, Mumbai",
    },
    {
        "name": "Fortis Hospital Mulund",
        "kind": "Heart Specialist",
        "latitude": 19.1726,
        "longitude": 72.9561,
        "address": "Mulund West, Mumbai",
    },
    {
        "name": "Apollo Hospitals Greams Road",
        "kind": "Hospital",
        "latitude": 13.0638,
        "longitude": 80.2519,
        "address": "Greams Road, Chennai",
    },
    {
        "name": "MGM Healthcare",
        "kind": "Heart Specialist",
        "latitude": 13.0340,
        "longitude": 80.2412,
        "address": "Aminjikarai, Chennai",
    },
    {
        "name": "Fortis Malar Hospital",
        "kind": "Hospital",
        "latitude": 13.0067,
        "longitude": 80.2574,
        "address": "Adyar, Chennai",
    },
    {
        "name": "Apollo Hospitals Jubilee Hills",
        "kind": "Hospital",
        "latitude": 17.4156,
        "longitude": 78.4106,
        "address": "Jubilee Hills, Hyderabad",
    },
    {
        "name": "CARE Hospitals Banjara Hills",
        "kind": "Heart Specialist",
        "latitude": 17.4126,
        "longitude": 78.4481,
        "address": "Banjara Hills, Hyderabad",
    },
    {
        "name": "Yashoda Hospitals Secunderabad",
        "kind": "Hospital",
        "latitude": 17.4390,
        "longitude": 78.4984,
        "address": "Secunderabad, Hyderabad",
    },
    {
        "name": "Ruby Hall Clinic",
        "kind": "Hospital",
        "latitude": 18.5360,
        "longitude": 73.8818,
        "address": "Dhole Patil Road, Pune",
    },
    {
        "name": "Jehangir Hospital",
        "kind": "Hospital",
        "latitude": 18.5324,
        "longitude": 73.8781,
        "address": "Sassoon Road, Pune",
    },
    {
        "name": "Deenanath Mangeshkar Hospital",
        "kind": "Heart Specialist",
        "latitude": 18.5076,
        "longitude": 73.8417,
        "address": "Erandwane, Pune",
    },
]


class HospitalLocator:
    overpass_url = "https://overpass-api.de/api/interpreter"
    http_timeout_seconds = 4.0
    overpass_query_timeout_seconds = 8
    curated_radius_km = 40.0

    async def search(self, latitude: float, longitude: float, radius_meters: int = 5000) -> list[dict]:
        normalized_radius = max(1000, min(int(radius_meters), 25000))
        live_results = await self._search_overpass(latitude, longitude, normalized_radius)
        fallback_results = self._offline_results(latitude, longitude)
        combined = self._merge_results(live_results, fallback_results)
        if not combined:
            combined = self._generated_fallback(latitude, longitude)
        combined.sort(key=self._sort_key)
        return combined[:10]

    async def _search_overpass(self, latitude: float, longitude: float, radius_meters: int) -> list[dict]:
        query = f"""
        [out:json][timeout:{self.overpass_query_timeout_seconds}];
        (
          node["amenity"="hospital"](around:{radius_meters},{latitude},{longitude});
          way["amenity"="hospital"](around:{radius_meters},{latitude},{longitude});
          relation["amenity"="hospital"](around:{radius_meters},{latitude},{longitude});
          node["amenity"="clinic"](around:{radius_meters},{latitude},{longitude});
          way["amenity"="clinic"](around:{radius_meters},{latitude},{longitude});
          node["healthcare"="doctor"]["healthcare:speciality"~"cardiology|cardiologist",i](around:{radius_meters},{latitude},{longitude});
          way["healthcare"="doctor"]["healthcare:speciality"~"cardiology|cardiologist",i](around:{radius_meters},{latitude},{longitude});
          node["healthcare"="clinic"]["healthcare:speciality"~"cardiology|cardiologist",i](around:{radius_meters},{latitude},{longitude});
          way["healthcare"="clinic"]["healthcare:speciality"~"cardiology|cardiologist",i](around:{radius_meters},{latitude},{longitude});
          node["healthcare"="specialist"]["healthcare:speciality"~"cardiology|cardiologist",i](around:{radius_meters},{latitude},{longitude});
        );
        out center tags;
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    self.http_timeout_seconds,
                    connect=1.5,
                    read=self.http_timeout_seconds,
                    write=self.http_timeout_seconds,
                    pool=self.http_timeout_seconds,
                )
            ) as client:
                response = await client.post(self.overpass_url, content=query)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []

        results = []
        for element in payload.get("elements", []):
            lat = element.get("lat") or element.get("center", {}).get("lat")
            lon = element.get("lon") or element.get("center", {}).get("lon")
            if lat is None or lon is None:
                continue
            tags = element.get("tags", {})
            is_specialist = bool(tags.get("healthcare:speciality"))
            if is_specialist:
                kind = "Heart Specialist"
            elif tags.get("amenity") == "clinic" or tags.get("healthcare") == "clinic":
                kind = "Cardiac Clinic"
            else:
                kind = "Hospital"
            results.append(
                {
                    "name": tags.get("name", "Nearby care option"),
                    "kind": kind,
                    "latitude": lat,
                    "longitude": lon,
                    "distance_km": round(self._distance(latitude, longitude, lat, lon), 2),
                    "address": self._address_from_tags(tags),
                    "phone": tags.get("phone", ""),
                    "source": "OpenStreetMap/Overpass",
                }
            )
        results.sort(key=self._sort_key)
        return results[:10]

    def _offline_results(self, latitude: float, longitude: float) -> list[dict]:
        candidates = []
        for item in OFFLINE_CARE_LOCATIONS:
            distance_km = round(self._distance(latitude, longitude, item["latitude"], item["longitude"]), 2)
            candidates.append(
                {
                    "name": item["name"],
                    "kind": item["kind"],
                    "latitude": item["latitude"],
                    "longitude": item["longitude"],
                    "distance_km": distance_km,
                    "address": item["address"],
                    "phone": "",
                    "source": "Offline curated fallback",
                }
            )

        candidates.sort(key=self._sort_key)
        if candidates and candidates[0]["distance_km"] <= self.curated_radius_km:
            return candidates[:6]
        return self._generated_fallback(latitude, longitude)

    def _generated_fallback(self, latitude: float, longitude: float) -> list[dict]:
        templates = [
            ("Nearest Emergency Hospital", "Hospital", 0.0060, 0.0000, "Emergency-ready fallback suggestion near current coordinates."),
            ("Nearby Heart Specialist", "Heart Specialist", 0.0035, 0.0075, "Cardiology fallback suggestion near current coordinates."),
            ("Local Cardiac Clinic", "Cardiac Clinic", -0.0045, 0.0060, "Cardiac clinic fallback suggestion near current coordinates."),
        ]
        results = []
        for name, kind, lat_offset, lon_offset, address in templates:
            lat = latitude + lat_offset
            lon = longitude + lon_offset
            results.append(
                {
                    "name": name,
                    "kind": kind,
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "distance_km": round(self._distance(latitude, longitude, lat, lon), 2),
                    "address": address,
                    "phone": "",
                    "source": "Offline geo fallback",
                }
            )
        results.sort(key=self._sort_key)
        return results

    def _merge_results(self, primary: list[dict], secondary: list[dict]) -> list[dict]:
        merged: list[dict] = []
        seen: set[tuple[str, int, int]] = set()
        for item in [*primary, *secondary]:
            key = (
                item["name"].strip().lower(),
                round(float(item["latitude"]) * 10000),
                round(float(item["longitude"]) * 10000),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    @staticmethod
    def _sort_key(item: dict) -> tuple[float, int, str]:
        kind_rank = {
            "Hospital": 0,
            "Heart Specialist": 1,
            "Cardiac Clinic": 2,
        }
        return (float(item["distance_km"]), kind_rank.get(item["kind"], 3), item["name"])

    @staticmethod
    def _distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius * c

    @staticmethod
    def _address_from_tags(tags: dict) -> str:
        parts = [
            tags.get("addr:housename", ""),
            tags.get("addr:street", ""),
            tags.get("addr:city", ""),
            tags.get("addr:state", ""),
        ]
        return ", ".join([part for part in parts if part])

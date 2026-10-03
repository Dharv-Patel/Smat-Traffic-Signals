"""
traffic_graph.py
Dijkstra shortest-path weighted by vehicle count (no density cap).
"""
import heapq
import math


class TrafficGraph:
    def __init__(self, junctions: dict, roads: list):
        self.junctions = junctions
        self.adj = {jid: [] for jid in junctions}
        for src, dst, dist in roads:
            self.adj[src].append((dst, dist))
            self.adj[dst].append((src, dist))

    def _congestion_weight(self, vehicles: int) -> float:
        """
        Convert vehicle count to a travel-time multiplier.
        0 vehicles → 1.0x (free flow), 120 vehicles → ~3.5x (heavy)
        Uses a soft log curve so very high counts don't explode.
        """
        return 1.0 + 2.5 * math.log1p(vehicles) / math.log1p(120)

    def shortest_path(self, src: str, dst: str, vehicle_map: dict) -> tuple:
        dist = {jid: float('inf') for jid in self.junctions}
        dist[src] = 0
        prev = {jid: None for jid in self.junctions}
        pq = [(0, src)]

        avg_speed_kmh = 30

        while pq:
            cost, u = heapq.heappop(pq)
            if cost > dist[u]:
                continue
            if u == dst:
                break
            for v, road_dist in self.adj[u]:
                cong     = self._congestion_weight(vehicle_map.get(v, 20))
                new_cost = dist[u] + road_dist * cong
                if new_cost < dist[v]:
                    dist[v] = new_cost
                    prev[v] = u
                    heapq.heappush(pq, (new_cost, v))

        path = []
        cur  = dst
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()

        if not path or path[0] != src:
            return [], 0, 0

        total_dist = 0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            for neighbor, d in self.adj[u]:
                if neighbor == v:
                    total_dist += d
                    break

        avg_veh = sum(vehicle_map.get(j, 20) for j in path) / len(path)
        effective_speed    = avg_speed_kmh / self._congestion_weight(avg_veh)
        total_time_minutes = (total_dist / effective_speed) * 60

        return path, total_dist, total_time_minutes

    def haversine(self, j1: str, j2: str) -> float:
        lat1 = math.radians(self.junctions[j1]["lat"])
        lng1 = math.radians(self.junctions[j1]["lng"])
        lat2 = math.radians(self.junctions[j2]["lat"])
        lng2 = math.radians(self.junctions[j2]["lng"])
        dlat, dlng = lat2 - lat1, lng2 - lng1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
        return 6371 * 2 * math.asin(math.sqrt(a))

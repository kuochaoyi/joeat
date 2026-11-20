"use client";
// Pick the meeting point on a map (OpenStreetMap tiles via Leaflet). Loaded client-side only (see the dynamic import in the page).
// A circle marks 鹽埕區, the only area with restaurant data: a pin outside it still works but every restaurant will be "far".
import "leaflet/dist/leaflet.css";
import type { Map as LeafletMap, CircleMarker } from "leaflet";
import { useEffect, useRef } from "react";

import { COVERAGE } from "@/lib/geo";

export default function MapPicker({ value, onPick }: { value: { lat: number; lon: number } | null; onPick: (lat: number, lon: number) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const pin = useRef<CircleMarker | null>(null);
  const cb = useRef(onPick);
  cb.current = onPick;

  useEffect(() => {
    let dead = false;
    (async () => {
      const L = (await import("leaflet")).default;
      if (dead || !box.current || map.current) return;
      const m = L.map(box.current).setView([value?.lat ?? COVERAGE.lat, value?.lon ?? COVERAGE.lon], 14);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(m);
      L.circle([COVERAGE.lat, COVERAGE.lon], { radius: COVERAGE.radiusM, color: "#e8590c", weight: 1, fillOpacity: 0.05, interactive: false }).addTo(m);
      m.on("click", (e) => cb.current(e.latlng.lat, e.latlng.lng));
      map.current = m;
      if (value) pin.current = L.circleMarker([value.lat, value.lon], { radius: 9, color: "#c92a2a", fillColor: "#c92a2a", fillOpacity: 0.9 }).addTo(m);
    })();
    return () => { dead = true; map.current?.remove(); map.current = null; pin.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    (async () => {
      const m = map.current;
      if (!m || !value) return;
      const L = (await import("leaflet")).default;
      if (pin.current) pin.current.setLatLng([value.lat, value.lon]);
      else pin.current = L.circleMarker([value.lat, value.lon], { radius: 9, color: "#c92a2a", fillColor: "#c92a2a", fillOpacity: 0.9 }).addTo(m);
      m.panTo([value.lat, value.lon]);
    })();
  }, [value]);

  return <div ref={box} data-testid="map" style={{ height: 280, borderRadius: 12, border: "1px solid var(--line)", overflow: "hidden" }} />;
}

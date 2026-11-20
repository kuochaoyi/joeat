// 鹽埕區 is the only area with restaurant data. Mirrors COVERAGE_* in backend/app/services/sessions.py.
export const COVERAGE = { lat: 22.6245, lon: 120.2815, radiusM: 3000 };

export function distanceM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000, rad = Math.PI / 180;
  const a = Math.sin(((lat2 - lat1) * rad) / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

import type { LatLngTuple } from 'leaflet'

export type Location = { name: string; region: string; center: LatLngTuple; zoom: number }

export const locations: Location[] = [
  { name: 'Guwahati', region: 'Assam, India', center: [26.16196, 91.76805], zoom: 10 },
  { name: 'Silchar', region: 'Assam, India', center: [24.79041, 92.79004], zoom: 10 },
  { name: 'Patna', region: 'Bihar, India', center: [25.62691, 85.12809], zoom: 10 },
  { name: 'Kolkata', region: 'West Bengal, India', center: [22.56958, 88.36913], zoom: 10 },
  { name: 'Dhaka', region: 'Bangladesh', center: [23.72501, 90.40663], zoom: 10 },
]

export const initialView: Location = {
  name: 'Brahmaputra Valley', region: 'Northeast India', center: [26.05, 92.08], zoom: 8,
}

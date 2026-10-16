// Photos for the popular-route cards (supplied by the team, resized to ≤800px, JPG + WebP).
// Keyed by what the photo shows, not by route, so config.ts can map any route to any photo.
import chennaiCentralJpg from '../assets/routes/chennai-central.jpg'
import chennaiCentralWebp from '../assets/routes/chennai-central.webp'
import coimbatoreJpg from '../assets/routes/coimbatore.jpg'
import coimbatoreWebp from '../assets/routes/coimbatore.webp'
import maduraiJpg from '../assets/routes/madurai.jpg'
import maduraiWebp from '../assets/routes/madurai.webp'
import tiruchirappalliJpg from '../assets/routes/tiruchirappalli.jpg'
import tiruchirappalliWebp from '../assets/routes/tiruchirappalli.webp'

export interface RouteImage { jpg: string; webp: string; alt: string }

export const ROUTE_IMAGES = {
  'chennai-central': { jpg: chennaiCentralJpg, webp: chennaiCentralWebp, alt: 'Chennai Central station clock tower' },
  coimbatore: { jpg: coimbatoreJpg, webp: coimbatoreWebp, alt: 'Hill temple near Coimbatore' },
  madurai: { jpg: maduraiJpg, webp: maduraiWebp, alt: 'Meenakshi Amman Temple gopuram, Madurai' },
  tiruchirappalli: { jpg: tiruchirappalliJpg, webp: tiruchirappalliWebp, alt: 'Rockfort temple, Tiruchirappalli' },
} as const satisfies Record<string, RouteImage>

export type RouteImageId = keyof typeof ROUTE_IMAGES

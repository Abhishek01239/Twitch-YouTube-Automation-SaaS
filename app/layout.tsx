import "./globals.css";
import type { Metadata } from "next";
export const metadata: Metadata={title:"ShortsFlow — Twitch to YouTube Automation",description:"Automate 4 Shorts and 1 video per day across connected YouTube channels."};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
# Product Brief Summary

> **HISTORICAL DOCUMENT (superseded for scope).** This summary described the
> original *backend-only* build loop (slices 0–13, closed). Its
> "Deferred/Future Scope" list applied to that loop only — frontend, mobile
> app, deployment, and **online-to-offline retargeting are all in the current
> MVP scope**. The binding scope baseline is
> `docs/Mobility_AdTech_MVP_Proposal_5_Month_Retargeting.docx` (see
> decisions-log **D11** and `docs/architecture.md`). Do not plan or bound new
> work from this file.

## Project

Mobility AdTech & Audience Attribution Platform

## Product Goal

Build the backend for a mobility advertising platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, the system ingests GPS movement data, and analytics support impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

## Product Vision

Create a measurable mobility advertising network that combines mobility media, GPS route analytics, exposure scoring, and future offline-to-online attribution.

## Core Concept

Advertisers place campaigns on shared ride vehicles. The platform tracks vehicle movement, estimates impressions, produces campaign analytics, and calculates dynamic driver compensation.

## MVP Scope From Brief

- Driver tracking
- GPS analytics
- Impression estimation
- Driver payouts
- Campaign management
- Advertiser dashboard support
- Heatmaps

## Build-Now Backend Areas

- Project foundation
- Auth and role foundation
- Admin, advertiser, and driver user foundations
- Advertiser organizations and accounts
- Driver profiles
- Vehicle profiles
- Campaign management
- Campaign creative metadata
- Campaign target zones and geofences
- Driver and vehicle campaign assignment and activation
- GPS/location ping ingestion
- Trip/session/route tracking
- Route analytics
- Impression estimation v1
- Driver payout calculation v1
- Driver earnings ledger
- Advertiser dashboard summary APIs
- Campaign reporting APIs
- Heatmap/geospatial aggregation APIs
- Basic fraud/anomaly flags
- Seed/demo data
- API documentation
- Tests/checks

## Suggested Technologies Mentioned In Brief

The client brief mentions React/Next.js, Flutter or React Native, Node.js or FastAPI, PostgreSQL, Redis, AWS/GCP, Docker, and Mapbox. No backend stack has been chosen or implemented locally. Pro owns the backend stack decision.

## Deferred/Future Scope (historical — applied to backend slices 0–13 only; superseded by D11)

- Offline-to-online retargeting
- Anonymous audience pooling
- AI/computer vision counting
- Advanced ML fraud detection
- Real automated driver payout settlement
- Frontend implementation
- Mobile app implementation
- Production cloud deployment

## Long-Term Vision

Build Africa's mobility audience and attribution network powered by mobility analytics and urban attention intelligence.

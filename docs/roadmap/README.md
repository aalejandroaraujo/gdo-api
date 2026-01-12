# GDO Health - Development Roadmap

## Overview

This roadmap outlines the phased approach to complete the GDO Health platform migration from Typebot to a fully Azure-native solution.

**Current Status:** Phase 1 complete - JWT authentication implemented and tested

---

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 0 | [Infrastructure](./00-infrastructure.md) | **COMPLETE** |
| 1 | [Simple Authentication](./01-simple-auth.md) | **COMPLETE** |
| 2 | [Function App Deployment](./02-function-app-deployment.md) | In Progress |
| 3 | [Microsoft Entra External ID](./03-entra-external-id.md) | Not Started |

---

## Quick Links

- [Infrastructure Guide](../../infrastructure/DEPLOYMENT-GUIDE.md)
- [API Documentation](../API.md)
- [Architecture Overview](../ARCHITECTURE.md)

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-12 | PostgreSQL over MariaDB | Better Azure integration, JSONB support, asyncpg driver |
| 2026-01-12 | Switzerland North region | GDPR compliance, data residency |
| 2026-01-12 | Skip Azure AD B2C | End of sale May 2025; migrate to Entra External ID |
| 2026-01-12 | Bearer token auth | Industry standard, works with any identity provider |

---

*Last updated: 2026-01-12*

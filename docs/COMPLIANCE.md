# Legal & Compliance

This document describes the compliance surface area of the project and how
operators should use the `apps.compliance` module to evidence that surface.

> Nothing in this document is legal advice. Consult counsel for your
> jurisdiction.

## 1. Why this exists

Deploying CCTV analytics — even privacy-preserving analytics — typically
attracts three categories of obligation:

1. **Written consent** from the data controller (your customer) that they
   have authority to deploy you on the relevant cameras.
2. **Camera ownership / lawful access** — your customer warrants that they
   own or have a contractual right to operate each camera.
3. **Data-processing terms** — both parties agree on the scope of processing
   ("analytics only; no raw footage retained; no facial recognition by
   default").

`apps.compliance.DataProcessingConsent` records all three on a single
immutable row, with provenance (acting user, IP address, user-agent,
terms version, timestamp).

## 2. Model

```
apps.compliance.DataProcessingConsent
├── organization       FK  → apps.organizations.Organization
├── accepted_by        FK  → User (the human who clicked accept)
├── written_consent          bool  (must be true to be valid)
├── camera_ownership         bool  (must be true to be valid)
├── data_processing_terms    bool  (must be true to be valid)
├── terms_version            str   (e.g. "1.0" — bump invalidates older)
├── ip_address               IP    (auto-stamped from request)
├── user_agent               str   (auto-stamped from request)
├── notes                    text  (free-form)
├── revoked_at               datetime nullable
└── created_at, updated_at
```

`is_valid` returns `True` iff all three affirmations are true and
`revoked_at` is null.

## 3. REST endpoint

```http
POST /api/compliance/consents/
Authorization: Bearer <admin or owner jwt>
Content-Type: application/json

{
  "organization":          "<org-uuid>",
  "written_consent":       true,
  "camera_ownership":      true,
  "data_processing_terms": true,
  "notes":                 "Signed during onboarding call 2026-05-30 with J. Doe"
}
```

Server populates `accepted_by`, `ip_address`, `user_agent`, `terms_version`.

Records are immutable — there is no `PATCH` or `PUT`. To revoke, an
administrator updates `revoked_at` via the Django admin; to refresh, create a
new row.

## 4. Permissions

`IsAuthenticated + IsOrgAdminOrReadOnly` — only `owner` or `admin` members
of an organisation can create consent rows for that organisation. Other
members and other organisations see nothing.

## 5. Terms versioning

`CONSENT_TERMS_VERSION` env var (default `"1.0"`). When you materially change
the terms text presented in your UI, bump the version. Existing rows are
unaffected, but you can write a query to find organisations whose latest
consent is below the current terms version and prompt them to re-accept.

```sql
SELECT o.id, o.name, MAX(c.terms_version) AS latest_signed
FROM organizations_organization o
LEFT JOIN compliance_dataprocessingconsent c
       ON c.organization_id = o.id AND c.revoked_at IS NULL
GROUP BY o.id, o.name
HAVING MAX(c.terms_version) IS DISTINCT FROM '1.1';
```

## 6. Recommended customer-facing terms text

Show this exact paragraph (or a translated equivalent) above the three
checkboxes in your UI:

> "I confirm that the organisation I represent owns or has the contractual
> right to operate the cameras connected to this service. We process footage
> only for analytics — people counting, occupancy, security events. Raw
> video is not retained; only aggregate metadata is stored. Facial
> recognition is disabled by default. Ownership of all footage remains with
> our organisation. I am authorised to accept these terms on behalf of my
> organisation."

## 7. Where consent fits in the lifecycle

| Stage | Required? |
|---|---|
| Sign-up / create organisation | Not yet |
| Add the first camera | **Required** — block via UI / middleware |
| Promote to a paid plan | Re-confirm if terms version changed |
| Enable facial-recognition env switch | Re-confirm with explicit FR clause |

A `ConsentEnforcementMiddleware` is an excellent next contribution — it would
return `403` from camera-creation endpoints when the org has no valid
consent. The hook point exists; the middleware is not enabled by default
because the right policy varies by deployer.

## 8. GDPR alignment notes

- **Legal basis** — typically Article 6(1)(f) "legitimate interests" for
  occupancy counting in commercial premises. Document your Legitimate
  Interest Assessment (LIA) separately.
- **DPIA** — required for systematic monitoring of publicly accessible
  areas. The default deployment (face blur on, no recognition, no video
  retention) materially lowers DPIA risk scoring.
- **Record of Processing Activities (RoPA)** — list the categories of data
  (aggregate counts, camera health), retention periods, recipients
  (channels: Slack/email/etc.), and any cross-border transfers (your LLM
  provider's region).
- **Article 22** — automated decision-making with legal effect. The system
  triggers operational alerts only; it does not make decisions about
  individuals.

## 9. Operator checklist before going live

- [ ] Consent record created for each organisation.
- [ ] Terms version pinned in `.env` matches the version shown in the UI.
- [ ] Signage at every camera location.
- [ ] DPIA on file for the deployer.
- [ ] Retention job scheduled (see [PRIVACY.md](PRIVACY.md) §5).
- [ ] Incident-response runbook references [SECURITY.md](../SECURITY.md) §12.

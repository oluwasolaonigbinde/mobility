# Hetzner release templates

Templates only (D44/D62, REQ-049/108). Nothing applied; no account, region,
credentials, server, bucket or DNS record is selected. Follow
[deployment-templates](../../docs/deployment-templates.md) for gates and setup.

Use [production.env.example](../../production.env.example) or
[staging.env.example](../../staging.env.example) with the **standalone**
[production Compose file](../../docker-compose.production.yml) and
[Caddyfile](../../Caddyfile). Supply immutable image digests and secrets from
outside Git; blank secrets deliberately prevent rendering an operational stack.
The scanner image must be an approved official ClamAV image supporting
`clamdcheck.sh` (the locally inspected 1.4 image does). No image is pulled here.

The existing path-style S3 adapter expects both storage endpoints to be
`https://<approved-location>.your-objectstorage.com`, region to be that approved
location, and the bucket in `OBJECT_STORAGE_BUCKET`. No AWS IAM or KMS is used.
Keep the bucket private, enable/verify versioning, isolate application keys in
a dedicated project or reviewed per-key bucket policy, and replace the exact
origin in [s3-cors.json](s3-cors.json) before any separately approved application.
Long-lived keys, signature updates, off-host backup and retention remain
operator responsibilities. Bank/NIN encryption stays in the application key ring.

MapTiler uses the complete approved HTTPS MapLibre style URL in
`NEXT_PUBLIC_MAP_STYLE_URL`; the public key must be restricted to the approved
browser origin. It is bundled into the frontend image and needs a rebuild to
change. No credential is present in the template. Residency is REQ-032's legal
decision, never a template default.

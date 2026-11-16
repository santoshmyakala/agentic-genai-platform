# Promoting a model image between environments

## Flow
1. A push to main of wine-quality-mlops runs the secure-container workflow: gitleaks, Semgrep, Trivy, SBOM, image scan, smoke test, push, keyless signing and SBOM attestation.
2. Copy the digest from the job summary and run the promote workflow with environment=dev. It verifies the signature and attestation before committing the digest to gitops/environments/dev.
3. Argo CD syncs dev automatically.
4. Promote to prod with environment=prod. Prod only accepts the digest currently running in dev; Argo CD syncs prod manually.

## Rollback
Run promote with the previous digest (prod still requires that digest to be in dev first, so promote it to dev, then prod). Git history of gitops/environments shows every previous digest.

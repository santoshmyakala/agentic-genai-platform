# Deployment blocked by Kyverno admission

## Symptoms
Argo CD shows a sync error or kubectl apply fails with "admission webhook denied the request" naming a Kyverno policy.

## By policy
- verify-image-signatures: the image is not signed by the secure-container workflow on main, or has no SBOM attestation. Images built locally or by another workflow are always denied. Rebuild through the pipeline and promote the new digest with the promote workflow.
- disallow-privileged, require-non-root, disallow-privilege-escalation: fix the pod securityContext (runAsNonRoot: true, allowPrivilegeEscalation: false).
- disallow-latest-tag: pin the image by digest (preferred) or an explicit tag.
- require-resources: add cpu and memory requests and a memory limit.
- require-probes: add livenessProbe and readinessProbe to every container.

## Do not
Do not exclude the namespace or switch the policy to Audit to get a deploy through. File an exception through review instead.

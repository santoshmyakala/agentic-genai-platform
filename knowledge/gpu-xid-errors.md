# GPU XID errors and hardware health

## Symptoms
The GPUXidError alert fires from dcgm-exporter (DCGM_FI_DEV_XID_ERRORS increased in the last 10 minutes). Training jobs on the node fail with CUDA errors or NCCL timeouts; other nodes in the same job hang at all-reduce.

## Triage by XID code
- XID 13 / 31 / 43: usually application faults (illegal memory access, page fault). Check the job, not the node. No cordon.
- XID 48: double-bit ECC error. Hardware. Cordon the node and run dcgmi diag -r 3.
- XID 63 / 64: ECC page retirement or row remapping event. If DCGM_FI_DEV_ROW_REMAP_PENDING > 0, a GPU reset is needed at the next drain.
- XID 74: NVLink error. Cordon and check NVLink status with nvidia-smi nvlink -s.
- XID 79: GPU has fallen off the bus. Cordon immediately; the node needs a reboot and possibly hardware replacement.

## Actions
1. For hardware-class XIDs (48, 74, 79) cordon the node so no new GPU pods or Slurm jobs land on it (Kubernetes: kubectl cordon; Slurm: scontrol update nodename=<node> state=drain reason="XID").
2. Let running jobs checkpoint and exit, then drain.
3. Run dcgmi diag -r 3. Open a hardware ticket with the XID history and diag output if it fails.
4. Uncordon only after diagnostics pass.

## Temperature
GPUHighTemperature fires above 85 °C for 10 minutes. Check data-centre airflow and fan status before cordoning; sustained thermal throttling reduces throughput but is not an immediate fault.

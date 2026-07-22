#!/usr/bin/env bash
# kube-saver generated patch commands

# prod/ReplicaSet/auth-svc-84c6cb7889
kubectl patch replicaset auth-svc-84c6cb7889 -n prod \
  --type=merge -p '{"spec":{"template":{"spec":{"containers":[{"resources":{"requests":{"cpu":"50m","memory":"64Mi"}}}]}}}}'

# prod/ReplicaSet/checkout-svc-669ffb9b96
kubectl patch replicaset checkout-svc-669ffb9b96 -n prod \
  --type=merge -p '{"spec":{"template":{"spec":{"containers":[{"resources":{"requests":{"cpu":"50m","memory":"64Mi"}}}]}}}}'

# prod/ReplicaSet/cart-svc-857b89f789
kubectl patch replicaset cart-svc-857b89f789 -n prod \
  --type=merge -p '{"spec":{"template":{"spec":{"containers":[{"resources":{"requests":{"cpu":"50m","memory":"64Mi"}}}]}}}}'

# prod/ReplicaSet/api-gateway-d57c5f75
kubectl patch replicaset api-gateway-d57c5f75 -n prod \
  --type=merge -p '{"spec":{"template":{"spec":{"containers":[{"resources":{"requests":{"cpu":"50m","memory":"64Mi"}}}]}}}}'

# staging/ReplicaSet/staging-worker-54b45b8dcf
kubectl patch replicaset staging-worker-54b45b8dcf -n staging \
  --type=merge -p '{"spec":{"template":{"spec":{"containers":[{"resources":{"requests":{"cpu":"50m","memory":"64Mi"}}}]}}}}'

# staging/ReplicaSet/staging-api-88d5896
kubectl patch replicaset staging-api-88d5896 -n staging \
  --type=merge -p '{"spec":{"template":{"spec":{"containers":[{"resources":{"requests":{"cpu":"50m","memory":"64Mi"}}}]}}}}'

# data/ReplicaSet/cache-f6c5c7759
kubectl patch replicaset cache-f6c5c7759 -n data \
  --type=merge -p '{"spec":{"template":{"spec":{"containers":[{"resources":{"requests":{"cpu":"50m","memory":"64Mi"}}}]}}}}'

# dev/ReplicaSet/dev-api-7c679b65c9
kubectl patch replicaset dev-api-7c679b65c9 -n dev \
  --type=merge -p '{"spec":{"template":{"spec":{"containers":[{"resources":{"requests":{"cpu":"50m","memory":"64Mi"}}}]}}}}'

# monitoring/ReplicaSet/dashboard-7d865bd986
kubectl patch replicaset dashboard-7d865bd986 -n monitoring \
  --type=merge -p '{"spec":{"template":{"spec":{"containers":[{"resources":{"requests":{"cpu":"50m","memory":"64Mi"}}}]}}}}'

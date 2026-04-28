# Déploiement BotDoctor sur Kubernetes

1. Construire et pousser l’image Docker (si besoin)
   ```sh
   docker build -t registry.example.com/botdoctor-supervision:latest .
   docker push registry.example.com/botdoctor-supervision:latest
   ```
2. Adapter l’image dans `k8s/botdoctor-deployment.yaml` (champ `image:`)
3. Déployer sur le cluster :
   ```sh
   kubectl apply -f k8s/
   kubectl get pods -l app=botdoctor
   kubectl get svc botdoctor
   ```
4. Vérifier les probes et logs :
   ```sh
   kubectl logs <pod>
   kubectl describe pod <pod>
   ```
5. Exposer le service (NodePort, Ingress, LoadBalancer selon besoin)

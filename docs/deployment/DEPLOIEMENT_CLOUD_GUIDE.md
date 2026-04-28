# Déploiement multi-cloud des dashboards Streamlit

Ce guide fournit des instructions prêtes à l’emploi pour déployer vos dashboards sur Azure Web App, AWS Elastic Beanstalk et Google Cloud Run.

## 1. Prérequis communs
- Dockerfile présent à la racine du projet
- requirements.txt à jour
- Compte cloud (Azure, AWS, GCP)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé localement

## 2. Azure Web App for Containers

### Build & Push
```sh
az acr login --name <votre-registry>
docker build -t <votre-registry>.azurecr.io/crypto-ai-dashboard:latest .
docker push <votre-registry>.azurecr.io/crypto-ai-dashboard:latest
```

### Déploiement
```sh
az webapp create --resource-group <groupe> --plan <plan-app> --name <nom-app> --deployment-container-image-name <votre-registry>.azurecr.io/crypto-ai-dashboard:latest
```

## 3. AWS Elastic Beanstalk

### Initialisation
```sh
pip install awsebcli
eb init -p docker crypto-ai-dashboard
```

### Déploiement
```sh
eb create crypto-ai-dashboard-env
eb open
```

## 4. Google Cloud Run

### Build & Deploy
```sh
gcloud builds submit --tag gcr.io/<votre-projet>/crypto-ai-dashboard
gcloud run deploy crypto-ai-dashboard --image gcr.io/<votre-projet>/crypto-ai-dashboard --platform managed --region europe-west1 --allow-unauthenticated
```

## 5. CI/CD (GitHub Actions)
- Ajoutez un job de build/push Docker dans `.github/workflows/ci.yml` selon la cible cloud.
- Utilisez les secrets GitHub pour stocker vos credentials cloud.

## 6. Accès
- L’URL du dashboard sera fournie par la plateforme cloud après déploiement.

---
Pour toute question, ouvrez une issue sur le repo GitHub ou consultez la documentation officielle de chaque cloud.

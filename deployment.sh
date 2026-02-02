# # !/bin/bash

# # # This script builds and deploys the application to Google Cloud Run
# # # using the source code in the current directory.

# # # It configures the service with a specific service account, secures it
# # # with Identity-Aware Proxy (IAP), and sets recommended operational parameters.

# # Make sure you have authenticated with gcloud and set the correct project:
gcloud auth login
gcloud config set project ecg-data-gold-dev

echo "Deploying paste-it-app to Cloud Run..."

# # Exit immediately if a command exits with a non-zero status.
set -e

# Define variables
VERSION="v1.0.0"
PROJECT_ID="ecg-data-gold-dev"
REGION="europe-west1"
SERVICE_NAME="paste-it-app"
REPO_NAME="paste-it-app" # Artifact Registry repo name
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:${VERSION}"

# echo "Authenticating Docker with Artifact Registry..."
gcloud auth configure-docker ${REGION}-docker.pkg.dev


# # Build Docker image
export VERSION=${VERSION}
echo "Building Docker image..."

# Create Artifact Registry repository if it doesn't exist
echo "Building Docker image..."
# gcloud artifacts repositories create paste-it-app \
#     --repository-format=docker \
#     --location=europe-west1 \
#     --description="Docker repository for PASTE IT APP" \
#     --project=ecg-data-gold-dev

gcloud builds submit \
  --region=europe-west1 \
  --gcs-source-staging-dir=gs://ecg-data-gold-dev-cloudbuild-ew1/source \
  --tag ${IMAGE_TAG}

# # Deploy to Cloud Run
echo "Deploying paste-it-app to Cloud Run..."
gcloud run deploy paste-it-app \
  --image=${IMAGE_TAG} \
  --region=${REGION} \
  --port 8080 \
  --memory 1Gi \
  --min-instances 1 \
  --project ${PROJECT_ID}
#   --allow-unauthenticated \

# # Grant accesses
echo "Granting access..."
EMAILS=("qianyucazelles@ecg.camp")

for email in "${EMAILS[@]}"; do
  gcloud beta iap web add-iam-policy-binding \
    --resource-type=cloud-run \
    --service=${SERVICE_NAME} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --member="user:${email}" \
    --role="roles/iap.httpsResourceAccessor" \
    --condition=None
done
Overview
========

This is a simple application leveraging several GCP Serverless services to
demonstrate how to write things up and build real-world applications

Getting Started
---------------


You should install:

- Docker
- gcloud

Once you've got docker, you can try building the container:

    $ docker build .

Now, let's set the project we'll be using:

    $ export PROJECT=...

As you're working through this guide, you'll need to enable several APIs and
services. You should be prompted to enable Cloud Build and Cloud Run your first
time through. For this demo you'll need to enable Cloud Firestore, which can be
done by viewing the Firestore page in the Cloud Console. You also need to
enable the Cloud Natural Language API.

- Cloud Build (auto-enabled by gcloud)
- Cloud Run (auto-enabled by gcloud)
- Cloud Firestore (you must enable via console)
- CLoud Natural Language API (you must enable via console)


Setting the default region (we're using "us-central1" here) will reduce
prompts:

    $ gcloud config set run/region us-central1


Now, let's build it and store it in GCR:

    $ gcloud builds submit --tag gcr.io/$PROJECT/run-demo-run

Now we can deploy to Cloud Run:

    $ gcloud beta run deploy --image gcr.io/rk-demo-site/run-demo-run --platform managed

You should be able to access the app at the url reported by gcloud.


Local Development
-----------------

You can run the container with

    $ docker run -e "PORT=9090" ...


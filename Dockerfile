FROM python:3.11-slim

WORKDIR /corelab_netapp

COPY requirements.txt requirements.txt
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir -r requirements.txt
RUN mkdir -p capif_onboarding
COPY src/ /corelab_netapp/
EXPOSE 5000
CMD ["sh", "/corelab_netapp/prepare.sh"]

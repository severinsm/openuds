# base image  
FROM python:3.10

# copy certs
run mkdir -p /etc/certs
copy ./certs /etc/certs

# setup environment variable  
ENV DockerHOME=/home/uds/tunnel

## add user
RUN useradd -rm -d /home/uds -s /bin/bash -g root -G sudo -u 1001 uds
USER uds


# set work directory 
RUN mkdir -p $DockerHOME   
WORKDIR $DockerHOME  

# set environment variables  
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1  

# upgrade pip installer 
RUN pip install --upgrade pip  

# copy whole project to your docker home directory. 
COPY . $DockerHOME  

# Install all dependencies  
RUN pip install -r requirements.txt  
# port where the tunnel app runs  
EXPOSE 7777
# start server  
CMD ["python", "./src/udstunnel.py", "-t"]
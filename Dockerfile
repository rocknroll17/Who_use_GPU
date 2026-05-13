FROM python:3.12-alpine
# gcompat: Alpine(musl)에서 호스트 nvidia-smi(glibc 바이너리) 실행 가능하게
RUN apk add --no-cache gcompat
WORKDIR /app
COPY gpu_monitor.py .
CMD ["python3", "-u", "gpu_monitor.py"]

# Imagen del experimento (canvas CD-006, sección S): Python 3.12 con el cliente de
# Docker, para apagar y prender gNa, y matplotlib para la gráfica.
FROM python:3.12-slim

COPY --from=docker:27.3.1-cli /usr/local/bin/docker /usr/local/bin/docker
RUN pip install --no-cache-dir matplotlib==3.9.2 pytest==9.2.0

ENV PYTHONUNBUFFERED=1
WORKDIR /experimento
COPY medir.py grafica.py test_medir.py ./

# Mide las corridas y luego hace la gráfica y la tabla resumen.
CMD ["sh", "-c", "python medir.py && python grafica.py"]

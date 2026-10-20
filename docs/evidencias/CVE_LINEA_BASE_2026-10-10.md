> **Evidencia histórica (10/10/2026).** Salida del escaneo de las imágenes originales, conservada sin cambios de contenido. No describe el estado actual.

# Línea base de vulnerabilidades críticas y altas (antes de las correcciones)

Generada con `docker scout cves --only-severity critical,high --format packages <imagen>` el 2026-10-10 sobre las imágenes
originales (primera versión de la contenerización). Para cada paquete: severidad, CVE y versión que lo corrige.
Estado actual y decisiones: [DESPLIEGUE.md](../DESPLIEGUE.md) §6.

## glucolume/backend (Debian 13 + Python 3.14.0)

### perl 5.40.1-6 — 4 críticas, 4 altas
- CRITICAL CVE-2026-12087 — corregida en: 5.40.1-6+deb13u1
- CRITICAL CVE-2026-13221 — corregida en: 5.40.1-6+deb13u1
- CRITICAL CVE-2026-42496 — corregida en: 5.40.1-6+deb13u1
- CRITICAL CVE-2026-8376 — corregida en: 5.40.1-6+deb13u1
- HIGH CVE-2026-42497 — corregida en: 5.40.1-6+deb13u1
- HIGH CVE-2026-48959 — corregida en: 5.40.1-6+deb13u1
- HIGH CVE-2026-48962 — corregida en: 5.40.1-6+deb13u1
- HIGH CVE-2026-57432 — corregida en: 5.40.1-6+deb13u1

### openssl 3.5.4-1~deb13u1 — 3 críticas, 18 altas
- CRITICAL CVE-2026-31789 — corregida en: 3.5.5-1~deb13u2
- CRITICAL CVE-2026-34182 — corregida en: 3.5.6-1~deb13u2
- CRITICAL CVE-2026-75803 — corregida en: 3.5.7-1~deb13u2
- HIGH CVE-2025-15467 — corregida en: 3.5.4-1~deb13u2
- HIGH CVE-2025-69419 — corregida en: 3.5.4-1~deb13u2
- HIGH CVE-2025-69420 — corregida en: 3.5.4-1~deb13u2
- HIGH CVE-2025-69421 — corregida en: 3.5.4-1~deb13u2
- HIGH CVE-2026-28387 — corregida en: 3.5.5-1~deb13u2
- HIGH CVE-2026-28388 — corregida en: 3.5.5-1~deb13u2
- HIGH CVE-2026-28389 — corregida en: 3.5.5-1~deb13u2
- HIGH CVE-2026-28390 — corregida en: 3.5.5-1~deb13u2
- HIGH CVE-2026-31790 — corregida en: 3.5.5-1~deb13u2
- HIGH CVE-2026-34180 — corregida en: 3.5.6-1~deb13u2
- HIGH CVE-2026-45445 — corregida en: 3.5.6-1~deb13u2
- HIGH CVE-2026-45447 — corregida en: 3.5.6-1~deb13u2
- HIGH CVE-2026-54874 — corregida en: 3.5.7-1~deb13u2
- HIGH CVE-2026-63072 — corregida en: 3.5.7-1~deb13u2
- HIGH CVE-2026-63076 — corregida en: 3.5.7-1~deb13u2
- HIGH CVE-2026-7383 — corregida en: 3.5.6-1~deb13u2
- HIGH CVE-2026-84782 — corregida en: 3.5.7-1~deb13u3
- HIGH CVE-2026-9076 — corregida en: 3.5.6-1~deb13u2

### glibc 2.41-12 — 1 críticas, 6 altas
- CRITICAL CVE-2026-5450 — corregida en: 2.41-12+deb13u4
- HIGH CVE-2025-15281 — corregida en: 2.41-12+deb13u2
- HIGH CVE-2026-0861 — corregida en: 2.41-12+deb13u2
- HIGH CVE-2026-0915 — corregida en: 2.41-12+deb13u2
- HIGH CVE-2026-4046 — corregida en: 2.41-12+deb13u3
- HIGH CVE-2026-4437 — corregida en: 2.41-12+deb13u3
- HIGH CVE-2026-5928 — corregida en: 2.41-12+deb13u4

### pcre2 10.46-1~deb13u1 — 0 críticas, 3 altas
- HIGH CVE-2026-103111 — corregida en: 10.46-1~deb13u3
- HIGH CVE-2026-86145 — corregida en: 10.46-1~deb13u2
- HIGH CVE-2026-89161 — corregida en: 10.46-1~deb13u2

### sqlite3 3.46.1-7 — 0 críticas, 2 altas
- HIGH CVE-2026-11822 — corregida en: 3.46.1-7+deb13u2
- HIGH CVE-2026-11824 — corregida en: 3.46.1-7+deb13u2

### zlib 1:1.3.dfsg+really1.3.1-1 — 0 críticas, 1 altas
- HIGH CVE-2026-85091 — corregida en: not fixed

### dpkg 1.22.21 — 0 críticas, 1 altas
- HIGH CVE-2026-2219 — corregida en: 1.22.22

## glucolume/frontend (nginx-unprivileged 1.28-alpine)

### curl 8.17.0-r1 — 10 críticas, 19 altas
- CRITICAL CVE-2026-10536 — corregida en: 8.22.0-r0
- CRITICAL CVE-2026-11564 — corregida en: 8.22.0-r0
- CRITICAL CVE-2026-11856 — corregida en: 8.22.0-r0
- CRITICAL CVE-2026-18924 — corregida en: 8.22.0-r0
- CRITICAL CVE-2026-19931 — corregida en: 8.22.0-r0
- CRITICAL CVE-2026-8924 — corregida en: 8.22.0-r0
- CRITICAL CVE-2026-8925 — corregida en: 8.22.0-r0
- CRITICAL CVE-2026-8926 — corregida en: 8.22.0-r0
- CRITICAL CVE-2026-8927 — corregida en: 8.22.0-r0
- CRITICAL CVE-2026-9079 — corregida en: 8.22.0-r0
- HIGH CVE-2026-11352 — corregida en: 8.22.0-r0
- HIGH CVE-2026-11586 — corregida en: 8.22.0-r0
- HIGH CVE-2026-12064 — corregida en: 8.22.0-r0
- HIGH CVE-2026-13608 — corregida en: 8.22.0-r0
- HIGH CVE-2026-3805 — corregida en: 8.19.0-r0
- HIGH CVE-2026-5773 — corregida en: 8.20.0-r0
- HIGH CVE-2026-6276 — corregida en: 8.20.0-r0
- HIGH CVE-2026-80229 — corregida en: 8.22.0-r0
- HIGH CVE-2026-80230 — corregida en: 8.22.0-r0
- HIGH CVE-2026-80231 — corregida en: 8.22.0-r0
- HIGH CVE-2026-80255 — corregida en: 8.22.0-r0
- HIGH CVE-2026-82208 — corregida en: 8.22.0-r0
- HIGH CVE-2026-82209 — corregida en: 8.22.0-r0
- HIGH CVE-2026-8286 — corregida en: 8.22.0-r0
- HIGH CVE-2026-8932 — corregida en: 8.22.0-r0
- HIGH CVE-2026-9080 — corregida en: 8.22.0-r0
- HIGH CVE-2026-9545 — corregida en: 8.22.0-r0
- HIGH CVE-2026-9546 — corregida en: 8.22.0-r0
- HIGH CVE-2026-9547 — corregida en: 8.22.0-r0

### openssl 3.5.5-r0 — 4 críticas, 20 altas
- CRITICAL CVE-2026-31789 — corregida en: 3.5.6-r0
- CRITICAL CVE-2026-34182 — corregida en: 3.5.7-r0
- CRITICAL CVE-2026-63073 — corregida en: 3.5.8-r0
- CRITICAL CVE-2026-75803 — corregida en: 3.5.8-r0
- HIGH CVE-2026-14456 — corregida en: 3.5.8-r0
- HIGH CVE-2026-14457 — corregida en: 3.5.8-r0
- HIGH CVE-2026-18798 — corregida en: 3.5.8-r0
- HIGH CVE-2026-28387 — corregida en: 3.5.6-r0
- HIGH CVE-2026-28388 — corregida en: 3.5.6-r0
- HIGH CVE-2026-28389 — corregida en: 3.5.6-r0
- HIGH CVE-2026-28390 — corregida en: 3.5.6-r0
- HIGH CVE-2026-31790 — corregida en: 3.5.6-r0
- HIGH CVE-2026-34180 — corregida en: 3.5.7-r0
- HIGH CVE-2026-34181 — corregida en: 3.5.7-r0
- HIGH CVE-2026-34183 — corregida en: 3.5.7-r0
- HIGH CVE-2026-42764 — corregida en: 3.5.7-r0
- HIGH CVE-2026-45445 — corregida en: 3.5.7-r0
- HIGH CVE-2026-45447 — corregida en: 3.5.7-r0
- HIGH CVE-2026-54874 — corregida en: 3.5.8-r0
- HIGH CVE-2026-63072 — corregida en: 3.5.8-r0
- HIGH CVE-2026-63075 — corregida en: 3.5.8-r0
- HIGH CVE-2026-63076 — corregida en: 3.5.8-r0
- HIGH CVE-2026-7383 — corregida en: 3.5.7-r0
- HIGH CVE-2026-9076 — corregida en: 3.5.7-r0

### nginx 1.28.2-r1 — 4 críticas, 8 altas
- CRITICAL CVE-2026-42055 — corregida en: 1.28.3-r4
- CRITICAL CVE-2026-42533 — corregida en: 1.28.3-r6
- CRITICAL CVE-2026-42945 — corregida en: 1.28.3-r1
- CRITICAL CVE-2026-9256 — corregida en: 1.28.3-r2
- HIGH CVE-2026-27651 — corregida en: 1.28.3-r0
- HIGH CVE-2026-27654 — corregida en: 1.28.3-r0
- HIGH CVE-2026-27784 — corregida en: 1.28.3-r0
- HIGH CVE-2026-32647 — corregida en: 1.28.3-r0
- HIGH CVE-2026-42946 — corregida en: 1.28.3-r1
- HIGH CVE-2026-49975 — corregida en: 1.28.3-r3
- HIGH CVE-2026-56434 — corregida en: 1.28.3-r6
- HIGH CVE-2026-60005 — corregida en: 1.28.3-r6

### expat 2.7.4-r0 — 1 críticas, 3 altas
- CRITICAL CVE-2026-32767 — corregida en: 2.7.5-r0
- HIGH CVE-2026-66046 — corregida en: 2.8.4-r0
- HIGH CVE-2026-76641 — corregida en: 2.8.4-r0
- HIGH CVE-2026-93990 — corregida en: 2.8.5-r0

### pcre2 10.47-r0 — 0 críticas, 3 altas
- HIGH CVE-2026-103111 — corregida en: 10.49-r0
- HIGH CVE-2026-86145 — corregida en: 10.48-r0
- HIGH CVE-2026-89161 — corregida en: 10.48-r0

### util-linux 2.41.2-r0 — 0 críticas, 3 altas
- HIGH CVE-2026-76642 — corregida en: 2.41.6-r0
- HIGH CVE-2026-78408 — corregida en: 2.41.6-r0
- HIGH CVE-2026-78410 — corregida en: 2.41.6-r0

### libpng 1.6.54-r0 — 0 críticas, 3 altas
- HIGH CVE-2026-25646 — corregida en: 1.6.55-r0
- HIGH CVE-2026-33416 — corregida en: 1.6.56-r0
- HIGH CVE-2026-33636 — corregida en: 1.6.56-r0

### zlib 1.3.1-r2 — 0 críticas, 1 altas
- HIGH CVE-2026-85091 — corregida en: 1.3.2-r1

### nghttp2 1.68.0-r0 — 0 críticas, 1 altas
- HIGH CVE-2026-27135 — corregida en: 1.68.1

### tiff 4.7.1-r0 — 0 críticas, 1 altas
- HIGH CVE-2026-4775 — corregida en: 4.7.2-r0

### c-ares 1.34.6-r0 — 0 críticas, 1 altas
- HIGH CVE-2026-33630 — corregida en: 1.34.8-r0

### libxml2 2.13.9-r0 — 0 críticas, 1 altas
- HIGH CVE-2026-86140 — corregida en: not fixed

### musl 1.2.5-r21 — 0 críticas, 1 altas
- HIGH CVE-2026-40200 — corregida en: 1.2.5-r23

## glucolume/firmware-build (Debian 13 + Arduino CLI 1.2.2)

### stdlib 1.19.3 — 8 críticas, 50 altas
- CRITICAL CVE-2023-24538 — corregida en: 1.19.8
- CRITICAL CVE-2023-24540 — corregida en: 1.19.9
- CRITICAL CVE-2024-24790 — corregida en: 1.21.11
- CRITICAL CVE-2025-22871 — corregida en: 1.23.8
- CRITICAL CVE-2025-68121 — corregida en: 1.24.13
- CRITICAL CVE-2026-39821 — corregida en: 1.25.13
- CRITICAL CVE-2026-56857 — corregida en: 1.26.9
- CRITICAL CVE-2026-78663 — corregida en: 1.26.9
- HIGH CVE-2022-30635 — corregida en: 1.22.7
- HIGH CVE-2022-41720 — corregida en: 1.19.4
- HIGH CVE-2022-41722 — corregida en: 1.19.6
- HIGH CVE-2022-41723 — corregida en: 1.19.6
- HIGH CVE-2022-41724 — corregida en: 1.19.6
- HIGH CVE-2022-41725 — corregida en: 1.19.6
- HIGH CVE-2023-24534 — corregida en: 1.19.8
- HIGH CVE-2023-24536 — corregida en: 1.19.8
- HIGH CVE-2023-24537 — corregida en: 1.19.8
- HIGH CVE-2023-24539 — corregida en: 1.19.9
- HIGH CVE-2023-29400 — corregida en: 1.19.9
- HIGH CVE-2023-29403 — corregida en: 1.19.10
- HIGH CVE-2023-39325 — corregida en: 1.20.10
- HIGH CVE-2023-44487 — corregida en: 1.20.10
- HIGH CVE-2023-45283 — corregida en: 1.20.11
- HIGH CVE-2023-45287 — corregida en: 1.20.0
- HIGH CVE-2023-45288 — corregida en: 1.21.9
- HIGH CVE-2024-24784 — corregida en: 1.21.8
- HIGH CVE-2024-24791 — corregida en: 1.21.12
- HIGH CVE-2024-34156 — corregida en: 1.22.7
- HIGH CVE-2024-34158 — corregida en: 1.22.7
- HIGH CVE-2025-58187 — corregida en: 1.24.9
- HIGH CVE-2025-58188 — corregida en: 1.24.8
- HIGH CVE-2025-61723 — corregida en: 1.24.8
- HIGH CVE-2025-61725 — corregida en: 1.24.8
- HIGH CVE-2025-61726 — corregida en: 1.24.12
- HIGH CVE-2025-61729 — corregida en: 1.24.11
- HIGH CVE-2026-25679 — corregida en: 1.25.8
- HIGH CVE-2026-32280 — corregida en: 1.25.9
- HIGH CVE-2026-32281 — corregida en: 1.25.9
- HIGH CVE-2026-32283 — corregida en: 1.25.9
- HIGH CVE-2026-33811 — corregida en: 1.25.10
- HIGH CVE-2026-33814 — corregida en: 1.25.10
- HIGH CVE-2026-33818 — corregida en: 1.25.13
- HIGH CVE-2026-39820 — corregida en: 1.25.10
- HIGH CVE-2026-39822 — corregida en: 1.25.12
- HIGH CVE-2026-39836 — corregida en: 1.25.10
- HIGH CVE-2026-42499 — corregida en: 1.25.10
- HIGH CVE-2026-42504 — corregida en: 1.25.11
- HIGH CVE-2026-56853 — corregida en: 1.25.13
- HIGH CVE-2026-56859 — corregida en: 1.25.13
- HIGH CVE-2026-56862 — corregida en: 1.25.13
- HIGH CVE-2026-56866 — corregida en: 1.26.9
- HIGH CVE-2026-78659 — corregida en: 1.26.9
- HIGH CVE-2026-78660 — corregida en: 1.26.9
- HIGH CVE-2026-78667 — corregida en: 1.26.9
- HIGH CVE-2026-78669 — corregida en: 1.26.9
- HIGH CVE-2026-94439 — corregida en: 1.26.9
- HIGH CVE-2026-94440 — corregida en: 1.26.9
- HIGH CVE-2026-97031 — corregida en: 1.26.9

### golang.org/x/crypto 0.37.0 — 7 críticas, 6 altas
- CRITICAL CVE-2026-39830 — corregida en: 0.52.0
- CRITICAL CVE-2026-39831 — corregida en: 0.52.0
- CRITICAL CVE-2026-39832 — corregida en: 0.52.0
- CRITICAL CVE-2026-39833 — corregida en: 0.52.0
- CRITICAL CVE-2026-39834 — corregida en: 0.52.0
- CRITICAL CVE-2026-42508 — corregida en: 0.52.0
- CRITICAL CVE-2026-46595 — corregida en: 0.52.0
- HIGH CVE-2025-47913 — corregida en: 0.43.0
- HIGH CVE-2026-39829 — corregida en: 0.52.0
- HIGH CVE-2026-46597 — corregida en: 0.52.0
- HIGH CVE-2026-56854 — corregida en: 0.55.0
- HIGH CVE-2026-56855 — corregida en: 0.56.0
- HIGH CVE-2026-78662 — corregida en: 0.56.0

### stdlib 1.24.1 — 5 críticas, 30 altas
- CRITICAL CVE-2025-22871 — corregida en: 1.24.2
- CRITICAL CVE-2025-68121 — corregida en: 1.24.13
- CRITICAL CVE-2026-39821 — corregida en: 1.25.13
- CRITICAL CVE-2026-56857 — corregida en: 1.26.9
- CRITICAL CVE-2026-78663 — corregida en: 1.26.9
- HIGH CVE-2025-22874 — corregida en: 1.24.4
- HIGH CVE-2025-58187 — corregida en: 1.24.9
- HIGH CVE-2025-58188 — corregida en: 1.24.8
- HIGH CVE-2025-61723 — corregida en: 1.24.8
- HIGH CVE-2025-61725 — corregida en: 1.24.8
- HIGH CVE-2025-61726 — corregida en: 1.24.12
- HIGH CVE-2025-61729 — corregida en: 1.24.11
- HIGH CVE-2026-25679 — corregida en: 1.25.8
- HIGH CVE-2026-32280 — corregida en: 1.25.9
- HIGH CVE-2026-32281 — corregida en: 1.25.9
- HIGH CVE-2026-32283 — corregida en: 1.25.9
- HIGH CVE-2026-33811 — corregida en: 1.25.10
- HIGH CVE-2026-33814 — corregida en: 1.25.10
- HIGH CVE-2026-33818 — corregida en: 1.25.13
- HIGH CVE-2026-39820 — corregida en: 1.25.10
- HIGH CVE-2026-39822 — corregida en: 1.25.12
- HIGH CVE-2026-39836 — corregida en: 1.25.10
- HIGH CVE-2026-42499 — corregida en: 1.25.10
- HIGH CVE-2026-42504 — corregida en: 1.25.11
- HIGH CVE-2026-56853 — corregida en: 1.25.13
- HIGH CVE-2026-56859 — corregida en: 1.25.13
- HIGH CVE-2026-56862 — corregida en: 1.25.13
- HIGH CVE-2026-56866 — corregida en: 1.26.9
- HIGH CVE-2026-78659 — corregida en: 1.26.9
- HIGH CVE-2026-78660 — corregida en: 1.26.9
- HIGH CVE-2026-78667 — corregida en: 1.26.9
- HIGH CVE-2026-78669 — corregida en: 1.26.9
- HIGH CVE-2026-94439 — corregida en: 1.26.9
- HIGH CVE-2026-94440 — corregida en: 1.26.9
- HIGH CVE-2026-97031 — corregida en: 1.26.9

### stdlib 1.25.2 — 4 críticas, 26 altas
- CRITICAL CVE-2025-68121 — corregida en: 1.25.7
- CRITICAL CVE-2026-39821 — corregida en: 1.25.13
- CRITICAL CVE-2026-56857 — corregida en: 1.26.9
- CRITICAL CVE-2026-78663 — corregida en: 1.26.9
- HIGH CVE-2025-58187 — corregida en: 1.25.3
- HIGH CVE-2025-61726 — corregida en: 1.25.6
- HIGH CVE-2025-61729 — corregida en: 1.25.5
- HIGH CVE-2026-25679 — corregida en: 1.25.8
- HIGH CVE-2026-32280 — corregida en: 1.25.9
- HIGH CVE-2026-32281 — corregida en: 1.25.9
- HIGH CVE-2026-32283 — corregida en: 1.25.9
- HIGH CVE-2026-33811 — corregida en: 1.25.10
- HIGH CVE-2026-33814 — corregida en: 1.25.10
- HIGH CVE-2026-33818 — corregida en: 1.25.13
- HIGH CVE-2026-39820 — corregida en: 1.25.10
- HIGH CVE-2026-39822 — corregida en: 1.25.12
- HIGH CVE-2026-39836 — corregida en: 1.25.10
- HIGH CVE-2026-42499 — corregida en: 1.25.10
- HIGH CVE-2026-42504 — corregida en: 1.25.11
- HIGH CVE-2026-56853 — corregida en: 1.25.13
- HIGH CVE-2026-56859 — corregida en: 1.25.13
- HIGH CVE-2026-56862 — corregida en: 1.25.13
- HIGH CVE-2026-56866 — corregida en: 1.26.9
- HIGH CVE-2026-78659 — corregida en: 1.26.9
- HIGH CVE-2026-78660 — corregida en: 1.26.9
- HIGH CVE-2026-78667 — corregida en: 1.26.9
- HIGH CVE-2026-78669 — corregida en: 1.26.9
- HIGH CVE-2026-94439 — corregida en: 1.26.9
- HIGH CVE-2026-94440 — corregida en: 1.26.9
- HIGH CVE-2026-97031 — corregida en: 1.26.9

### stdlib 1.26.0 — 3 críticas, 26 altas
- CRITICAL CVE-2026-39821 — corregida en: 1.26.6
- CRITICAL CVE-2026-56857 — corregida en: 1.26.9
- CRITICAL CVE-2026-78663 — corregida en: 1.26.9
- HIGH CVE-2026-25679 — corregida en: 1.26.1
- HIGH CVE-2026-27137 — corregida en: 1.26.1
- HIGH CVE-2026-32280 — corregida en: 1.26.2
- HIGH CVE-2026-32281 — corregida en: 1.26.2
- HIGH CVE-2026-32283 — corregida en: 1.26.2
- HIGH CVE-2026-33810 — corregida en: 1.26.2
- HIGH CVE-2026-33811 — corregida en: 1.26.3
- HIGH CVE-2026-33814 — corregida en: 1.26.3
- HIGH CVE-2026-33818 — corregida en: 1.26.6
- HIGH CVE-2026-39820 — corregida en: 1.26.3
- HIGH CVE-2026-39822 — corregida en: 1.26.5
- HIGH CVE-2026-39836 — corregida en: 1.26.3
- HIGH CVE-2026-42499 — corregida en: 1.26.3
- HIGH CVE-2026-42504 — corregida en: 1.26.4
- HIGH CVE-2026-46600 — corregida en: 1.26.6
- HIGH CVE-2026-56853 — corregida en: 1.26.6
- HIGH CVE-2026-56859 — corregida en: 1.26.6
- HIGH CVE-2026-56862 — corregida en: 1.26.6
- HIGH CVE-2026-56866 — corregida en: 1.26.9
- HIGH CVE-2026-78659 — corregida en: 1.26.9
- HIGH CVE-2026-78660 — corregida en: 1.26.9
- HIGH CVE-2026-78667 — corregida en: 1.26.9
- HIGH CVE-2026-78669 — corregida en: 1.26.9
- HIGH CVE-2026-94439 — corregida en: 1.26.9
- HIGH CVE-2026-94440 — corregida en: 1.26.9
- HIGH CVE-2026-97031 — corregida en: 1.26.9

### golang.org/x/net 0.39.0 — 2 críticas, 5 altas
- CRITICAL CVE-2026-39821 — corregida en: 0.55.0
- CRITICAL CVE-2026-78663 — corregida en: 0.60.0
- HIGH CVE-2026-33814 — corregida en: 0.53.0
- HIGH CVE-2026-46600 — corregida en: 0.56.0
- HIGH CVE-2026-78659 — corregida en: 0.60.0
- HIGH CVE-2026-78660 — corregida en: 0.60.0
- HIGH CVE-2026-78669 — corregida en: 0.60.0

### gnutls28 3.8.9-3+deb13u4 — 2 críticas, 3 altas
- CRITICAL CVE-2026-88647 — corregida en: not fixed
- CRITICAL CVE-2026-95210 — corregida en: not fixed
- HIGH CVE-2026-67693 — corregida en: not fixed
- HIGH CVE-2026-95184 — corregida en: not fixed
- HIGH CVE-2026-95209 — corregida en: not fixed

### google.golang.org/grpc 1.72.0 — 1 críticas, 3 altas
- CRITICAL CVE-2026-33186 — corregida en: 1.79.3
- HIGH CVE-2026-84304 — corregida en: 1.83.1
- HIGH CVE-2026-84445 — corregida en: 1.82.2
- HIGH GHSA-hrxh-6v49-42gf — corregida en: 1.82.1

### golang.org/x/net 0.56.0 — 1 críticas, 3 altas
- CRITICAL CVE-2026-78663 — corregida en: 0.60.0
- HIGH CVE-2026-78659 — corregida en: 0.60.0
- HIGH CVE-2026-78660 — corregida en: 0.60.0
- HIGH CVE-2026-78669 — corregida en: 0.60.0

### github.com/go-git/go-git/v5 5.16.0 — 0 críticas, 2 altas
- HIGH CVE-2026-45022 — corregida en: 5.19.0
- HIGH CVE-2026-71556 — corregida en: 5.19.2

### golang.org/x/text 0.24.0 — 0 críticas, 1 altas
- HIGH CVE-2026-56851 — corregida en: 0.41.0

### github.com/go-git/go-billy/v5 5.6.2 — 0 críticas, 1 altas
- HIGH CVE-2026-44973 — corregida en: 5.9.0

### cyrus-sasl2 2.1.28+dfsg1-9 — 0 críticas, 1 altas
- HIGH CVE-2026-107161 — corregida en: not fixed

### zlib 1:1.3.dfsg+really1.3.1-1 — 0 críticas, 1 altas
- HIGH CVE-2026-85091 — corregida en: not fixed

## mcr.microsoft.com/mssql/server:2022-CU16-ubuntu-22.04

### openssl 3.0.2-0ubuntu1.18 — 0 críticas, 2 altas
- HIGH CVE-2026-45447 — corregida en: 3.0.2-0ubuntu1.25
- HIGH CVE-2026-84782 — corregida en: 3.0.2-0ubuntu1.30

### gnupg2 2.2.27-3ubuntu2.1 — 0 críticas, 1 altas
- HIGH CVE-2025-68973 — corregida en: 2.2.27-3ubuntu2.5

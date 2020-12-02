# Sonar 🐳

Work with multiple Docker images easily.

**Sonar is currently Work in Progress!**

## What is Sonar

Sonar is a tool that allows you to easily produce, template, build and publish
Dockerfiles and Docker images. It uses a declarative, multi-stage approach to
build Docker images.

## Quick start

Sonar can be used as a Python module or as a standalone program. Sonar will look
for an `inventory.yaml` file in your local directory that should contain a
collection of images to build and stages for each one of those images.

Sonar comes with an inventory file to be able to build itself, and to run its
unit tests. This [inventory.yaml](inventory.yaml) is:

``` yaml
vars:
  # start a local Docker registry with:
  # docker run -d -p 5000:5000 --restart=always --name registry registry:2
  registry: localhost:5000

images:
- name: sonar-test-runner

  vars:
    context: .

  # First stage builds a Docker image. The resulting image will be
  # pushed to the registry in the `output` section.
  stages:
  - name: build-sonar-tester-image
    task_type: docker_build

    dockerfile: docker/Dockerfile

    output:
    - registry: $(inputs.params.registry)/sonar-tester-image
      tag: $(inputs.params.version_id)

  # Second stage pushes the previously built image into a new
  # registry.
  - name: tag-image
    task_type: tag_image

    source:
      registry: $(inputs.params.registry)/sonar-tester-image
      tag: $(inputs.params.version_id)

    destination:
    - registry: $(inputs.params.registry)/sonar-tester-image-copy
      tag: $(inputs.params.version_id)

```

To execute this inventory file, you can do:

```
$ python sonar.py --image sonar-test-runner

image_build_start: sonar-test-runner
Stage started build-sonar-tester-image: 1/1
docker-image-push: localhost:5000/sonar-tester-image:799170de-74a0-4310-a674-d704b83f2ed2
```

At the end of this phase, you'll have a Docker image tagged as `localhost:5000/sonar-tester-image:799170de-74a0-4310-a674-d704b83f2ed2`
that you will be able to run with:

```
$ docker run localhost:5000/sonar-tester-image:799170de-74a0-4310-a674-d704b83f2ed2
============================= test session starts ==============================
platform linux -- Python 3.7.9, pytest-6.1.2, py-1.9.0, pluggy-0.13.1
rootdir: /src
collected 20 items

test/test_context.py ......x                                             [ 35%]
test/test_sonar.py .                                                     [ 40%]
test/test_tag_image.py .                                                 [ 45%]
test/test_tags.py ...........                                            [100%]

======================== 19 passed, 1 xfailed in 0.50s =========================
```


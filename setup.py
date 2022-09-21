import setuptools

# Read all requirements with versions from requirements.txt
requirements = {}
for line in open("requirements.txt").readlines():
    if "==" not in line or line.strip().startswith("#"):
        continue
    line = line.split("--hash", maxsplit=1)[0].strip(" \t\\\r\n").split("==", 1)
    requirements[line[0]] = line[1]

# Check for "[grpc]" packages and remove the non-"[grpc]"-version of them
for req in list(requirements.keys()):
    if (pos := req.find("[grpc]")) > 0:
        if req[:pos] in requirements:
            del requirements[req[:pos]]

setuptools.setup(
    package_dir={'viur': '.'},
    packages=[f'viur.{mod}' for mod in setuptools.find_packages('.', exclude=('tests*',))],
    install_requires=[f"{k}=={v}" for k, v in sorted(requirements.items(), key=lambda k: k[0].lower())]
)

import setuptools

# Read all requirements with versions from requirements.txt
install_requires = {}
for line in open("requirements.txt").readlines():
    if "==" not in line or line.strip().startswith("#"):
        continue
    line = line.split("--hash", maxsplit=1)[0].strip(" \t\\\r\n").split("==", 1)
    install_requires[line[0]] = line[1]

setuptools.setup(
    install_requires=[f"{k}=={v}" for k, v in sorted(install_requires.items(), key=lambda k: k[0].lower())]
)

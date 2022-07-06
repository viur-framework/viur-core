import setuptools

setuptools.setup(
    package_dir={'viur': '.'},
    packages=[f'viur.{mod}' for mod in setuptools.find_packages('.', exclude=('tests*',))],
    install_requires=sorted([
        line.split(maxsplit=1)[0].strip(" \t;")
        for line in open("requirements.txt").readlines()
        if "==" in line and not line.strip().startswith("#")
    ], key=lambda k: k.lower())
)

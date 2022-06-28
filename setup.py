import setuptools

setuptools.setup(
    package_dir={'viur': '.'},
    packages=[f'viur.{mod}' for mod in setuptools.find_packages('.', exclude=('tests*',))]
)

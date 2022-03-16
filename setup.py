import setuptools

setuptools.setup(packages=[f'viur.{mod}' for mod in setuptools.find_packages('.')])

from viur.core.bones import baseBone

class codeBone(baseBone):
	'''
		The codebone does not check and excaped the entered content.
		This can lead to security problems.
		Therefore, like the basebone, use this bone with caution.
	'''
	type = "code"

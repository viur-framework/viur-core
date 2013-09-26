from default import Render as default
from user import Render as user

def index( *args,  **kwargs ):
	render = default()
	tpl = render.getEnv().get_template( render.getTemplateFileName( "index" ) )
	return( tpl.render() )
index.exposed=True


def dumpAdminConfig( adminTree ):
	res = {}
	for key in dir( adminTree ):
		app = getattr( adminTree, key )
		if "adminInfo" in dir( app ) and app.adminInfo:
			res[ key ] = app.adminInfo
	return( res )

def _postProcessAppObj( obj ):
	obj.index = index
	adminConfig = dumpAdminConfig( obj )
	tmp = lambda *args, **kwargs: adminConfig
	tmp.internalExposed = True
	obj.config = tmp
	return obj

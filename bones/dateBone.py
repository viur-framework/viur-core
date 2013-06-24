# -*- coding: utf-8 -*-
from server.bones import baseBone
from server import request
from time import time, mktime
from datetime import time, datetime, timedelta
import logging
try:
	import pytz
except:
	pytz = None


## Workaround for Python Bug #7980 - time.strptime not thread safe
datetime.now().strptime("2010%02d%02d"%(1,1),"%Y%m%d")
datetime.now().strftime("%Y%m%d")

class ExtendedDateTime( datetime ):
	def totimestamp( self ):
		"""Converts this DateTime-Object back into Unixtime"""
		return( int( round( mktime( self.timetuple() ) ) ) )
		 
	def strftime(self, format ):
		"""
		Provides correct localized names for directives like %a which dont get translated on GAE properly
		This currently replaces %a, %A, %b, %B, %c, %x and %X.
		@param format: Strinc containing the Format to apply.
		@type format: string
		@returns: string
		"""
		if "%c" in format:
			format = format.replace("%c", _("const_datetimeformat") )
		if "%x" in format:
			format = format.replace("%x", _("const_dateformat") )
		if "%X" in format:
			format = format.replace("%X", _("const_timeformat") )
		if "%a" in format:
			format = format.replace( "%a", _("const_day_%s_short" % int( super( ExtendedDateTime, self ).strftime("%w") ) ) )
		if "%A" in format:
			format = format.replace( "%A", _("const_day_%s_long" % int( super( ExtendedDateTime, self ).strftime("%w") ) ) )
		if "%b" in format:
			format = format.replace( "%b", _("const_month_%s_short" % int( super( ExtendedDateTime, self ).strftime("%m") ) ) )
		if "%B" in format:
			format = format.replace( "%B", _("const_month_%s_long" % int( super( ExtendedDateTime, self ).strftime("%m") ) ) )
		return( super( ExtendedDateTime, self ).strftime( format.encode("UTF-8") ).decode("UTF-8") )

class dateBone( baseBone ):
	type = "date"
	
	def __init__( self,  creationMagic=False, updateMagic=False, date=True, time=True,  localize=False, *args,  **kwargs ):
		"""
			Initializes a new dateBone.
			
			@param creationMagic: Use the current time as value when creating an entity; ignoring this bone if the entity gets updated.
			@type creationMagic: Bool
			@param updateMagic: Use the current time whenever this entity is saved. 
			@type updateMagic: Bool
			@param date: Should this bone contain a date-information?
			@type date: Bool
			@param time: Should this bone contain time information?
			@type time: Bool
			@param localize: Automatically convert this time into the users timezone? Only valid if this bone contains date and time-information!
			@type localize: Bool
		"""
		baseBone.__init__( self,  *args,  **kwargs )
		if creationMagic or updateMagic:
			self.readonly = True
			self.visible = False
		self.creationMagic = creationMagic
		self.updateMagic = updateMagic
		if not( date or time ):
			raise ValueError("Attempt to create an empty datebone! Set date or time to True!")
		if localize and not ( date and time ):
			raise ValueError("Localization is only possible with date and time!")
		self.date=date
		self.time=time
		self.localize = localize

	def fromClient( self, name, data ):
		"""
			Reads a value from the client.
			If this value is valis for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.
			
			@param name: Our name in the skeleton
			@type name: String
			@param data: *User-supplied* request-data
			@type data: Dict
			@returns: None or String
		"""
		if name in data.keys():
			value = data[ name ]
		else:
			value = None
		self.value = None
		if str( value ).replace("-",  "",  1).replace(".","",1).isdigit():
			if int(value) < -1*(2**30) or int(value)>(2**31)-2:
				return( "Invalid value entered" )
			self.value = ExtendedDateTime.fromtimestamp( float(value) )
			return( None )
		elif not self.date and self.time:
			try:
				if str( value ).count(":")>1:
					(hour, minute, second) = [int(x.strip()) for x in str( value ).split(":")]
					self.value = time( hour=hour, minute=minute, second=second )
					return( None )
				elif str( value ).count(":")>0:
					(hour, minute) = [int(x.strip()) for x in str( value ).split(":")]
					self.value = time( hour=hour, minute=minute )
					return( None )
				elif str( value ).replace("-",  "",  1).isdigit():
					self.value = time( second=int(value) )
					return( None )
			except:
				return( "Invalid value entered" )
			return( False )
		elif str( value ).lower().startswith("now"):
			tmpRes = ExtendedDateTime.now()
			if len( str( value ) )>4:
				try:
					tmpRes += timedelta( seconds= int( str(value)[3:] ) )
				except:
					pass
			self.value = tmpRes
			return( None )
		else:
			try:
				if " " in value: # Date with time
					try: #Times with seconds
						if "-" in value: #ISO Date
							self.value = ExtendedDateTime.strptime(str( value ), "%Y-%m-%d %H:%M:%S")
						elif "/" in value: #Ami Date
							self.value = ExtendedDateTime.strptime(str( value ), "%m/%d/%Y %H:%M:%S")
						else: # European Date
							self.value = ExtendedDateTime.strptime(str( value ), "%d.%m.%Y %H:%M:%S")
					except:
						if "-" in value: #ISO Date
							self.value = ExtendedDateTime.strptime(str( value ), "%Y-%m-%d %H:%M")
						elif "/" in value: #Ami Date
							self.value = ExtendedDateTime.strptime(str( value ), "%m/%d/%Y %H:%M")
						else: # European Date
							self.value = ExtendedDateTime.strptime(str( value ), "%d.%m.%Y %H:%M")
				else:
					if "-" in value: #ISO Date
						self.value = ExtendedDateTime.strptime(str( value ), "%Y-%m-%d")
					elif "/" in value: #Ami Date
						self.value = ExtendedDateTime.strptime(str( value ), "%m/%d/%Y")
					else:
						self.value =ExtendedDateTime.strptime(str( value ), "%d.%m.%Y")
				return( None )
			except:
				return( "Invalid value entered" )
			return( "Invalid value entered" )

	def guessTimeZone(self):
		"""
		Guess the timezone the user is supposed to be in.
		If it cant be guessed, a safe default (UTC) is used
		"""
		timeZone = "UTC" # Default fallback
		try:
			#Check the local cache first
			if "timeZone" in request.current.requestData().keys():
				return( request.current.requestData()["timeZone"] )
			headers = request.current.get().request.headers
			if "X-Appengine-Country" in headers.keys():
				country = headers["X-Appengine-Country"]
			else: # Maybe local development Server - no way to guess it here
				return( timeZone )
			tzList = pytz.country_timezones[ country ]
		except: #Non-User generated request (deferred call; task queue etc), or no pytz
			return( timeZone )
		if len( tzList ) == 1: # Fine - the country has exactly one timezone
			timeZone = tzList[ 0 ]
		elif country.lower()=="us": # Fallback for the US
			timeZone = "EST"
		else: #The user is in a Country which has more than one timezone
			pass
		request.current.requestData()["timeZone"] = timeZone #Cache the result
		return( timeZone ) 

	def readLocalized(self, value ):
		"""Read a (probably localized Value) from the Client and convert it back to UTC"""
		res = value
		if not self.localize or not value or not isinstance( value, datetime) :
			return( res )
		#Nomalize the Date to UTC
		timeZone = self.guessTimeZone()
		if timeZone!="UTC" and pytz:
			utc = pytz.utc
			tz = pytz.timezone( timeZone )
			#FIXME: This is ugly as hell.
			# Parsing a Date which is inside DST of the given tz dosnt change the tz-info,
			# and normalizing the whole thing changes the other values, too
			# So we parse the whole thing, normalize it (=>get the correct DST-Settings), then replacing the parameters again
			# and pray that the DST-Settings are still valid..
			res = ExtendedDateTime(value.year, value.month, value.day, value.hour, value.minute, value.second, tzinfo=tz)
			res = tz.normalize( res ) #Figure out if its in DST or not
			res = res.replace( year=value.year, month=value.month, day=value.day, hour=value.hour, minute=value.minute, second=value.second ) #Reset the original values
			res = utc.normalize( res.astimezone( utc ) )
		return( res )

	def serialize( self, name, entity ):
		res = self.value
		if (self.creationMagic and not self.value) or self.updateMagic:
			res  = datetime.now() #This is UTC - Nothing to do here
		elif res:
			res = self.readLocalized( datetime.now().strptime( res.strftime( "%d.%m.%Y %H:%M:%S" ), "%d.%m.%Y %H:%M:%S"  ) )
		entity.set( name, res, self.indexed )
		return( entity )

	def unserialize( self, name, expando ):
		if not name in expando.keys():
			self.value = None
			return
		self.value = expando[ name ]
		if self.value and ( isinstance( self.value, float) or isinstance( self.value, int) ):
			if self.date:
				self.setLocalized( ExtendedDateTime.fromtimestamp( self.value ) )
			else:
				self.value = time( hour=int(self.value/60), minute=int(self.value%60) )
		elif isinstance( self.value, datetime ):
			self.setLocalized( ExtendedDateTime.now().strptime( self.value.strftime( "%d.%m.%Y %H:%M:%S" ), "%d.%m.%Y %H:%M:%S") )
		return
	
	def setLocalized( self, value ):
		""" Converts a Date read from DB (UTC) to the requesters local time"""
		self.value = value
		if not self.localize or not value or not isinstance( value, ExtendedDateTime) :
			return
		timeZone = self.guessTimeZone()
		if timeZone!="UTC" and pytz:
			utc = pytz.utc
			tz = pytz.timezone( timeZone )
			value = tz.normalize( value.replace( tzinfo=utc).astimezone( tz ) )
		self.value = value

	def buildDBFilter( self, name, skel, dbFilter, rawFilter ):
		for key in [ x for x in rawFilter.keys() if x.startswith(name) ]:
			if not self.fromClient( key, rawFilter ): #Parsing succeeded
				super( dateBone, self ).buildDBFilter( name, skel, dbFilter, {key:datetime.now().strptime( self.value.strftime( "%d.%m.%Y %H:%M:%S" ), "%d.%m.%Y %H:%M:%S"  )} )
		return( dbFilter )

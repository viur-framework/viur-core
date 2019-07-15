# -*- coding: utf-8 -*-
from server.bones.selectBone import selectBone
from collections import OrderedDict

ISO3CODES = {
	"abw": "Aruba",
	"afg": "Afghanistan",
	"ago": "Angola",
	"aia": "Anguilla",
	"alb": "Albania",
	"and": "Andorra",
	"ant": "Netherlands Antilles",
	"are": "United Arab Emirates",
	"arg": "Argentina",
	"arm": "Armenia",
	"asm": "American Samoa",
	"ata": "Antarctica",
	"atf": "French Southern Territories",
	"atg": "Antigua and Barbuda",
	"aus": "Australia",
	"aut": "Austria",
	"aze": "Azerbaijan",
	"bdi": "Burundi",
	"bel": "Belgium",
	"ben": "Benin",
	"bfa": "Burkina Faso",
	"bgd": "Bangladesh",
	"bgr": "Bulgaria",
	"bhr": "Bahrain",
	"bhs": "Bahamas",
	"bih": "Bosnia and Herzegovina",
	"blm": "Saint Barthelemy",
	"blr": "Belarus",
	"blz": "Belize",
	"bmu": "Bermuda",
	"bol": "Bolivia",
	"bra": "Brazil",
	"brb": "Barbados",
	"brn": "Brunei",
	"btn": "Bhutan",
	"bvt": "Bouvet Island",
	"bwa": "Botswana",
	"caf": "Central African Republic",
	"can": "Canada",
	"cck": "Cocos Islands",
	"che": "Switzerland",
	"chl": "Chile",
	"chn": "China",
	"civ": "Ivory Coast",
	"cmr": "Cameroon",
	"cod": "Congo Democratic Republic",
	"cog": "Congo Republic",
	"cok": "Cook Islands",
	"col": "Colombia",
	"com": "Comoros",
	"cpv": "Cape Verde",
	"cri": "Costa Rica",
	"cub": "Cuba",
	"cxr": "Christmas Island",
	"cym": "Cayman Islands",
	"cyp": "Cyprus",
	"cze": "Czech Republic",
	"deu": "Germany",
	"dji": "Djibouti",
	"dma": "Dominica",
	"dnk": "Denmark",
	"dom": "Dominican Republic",
	"dza": "Algeria",
	"ecu": "Ecuador",
	"egy": "Egypt",
	"eri": "Eritrea",
	"esh": "Western Sahara",
	"esp": "Spain",
	"est": "Estonia",
	"eth": "Ethiopia",
	"fin": "Finland",
	"fji": "Fiji",
	"flk": "Falkland Islands",
	"fra": "France",
	"fro": "Faroe Islands",
	"fsm": "Micronesia",
	"gab": "Gabon",
	"gbr": "United Kingdom",
	"geo": "Georgia",
	"ggy": "Guernsey",
	"gha": "Ghana",
	"gib": "Gibraltar",
	"gin": "Guinea",
	"gmb": "Gambia",
	"gnb": "Guinea-Bissau",
	"gnq": "Equatorial Guinea",
	"grc": "Greece",
	"grd": "Grenada",
	"grl": "Greenland",
	"gtm": "Guatemala",
	"gum": "Guam",
	"guy": "Guyana",
	"hkg": "Hong Kong",
	"hmd": "Heard Island and McDonald Islands",
	"hnd": "Honduras",
	"hrv": "Croatia",
	"hti": "Haiti",
	"hun": "Hungary",
	"idn": "Indonesia",
	"imn": "Isle of Man",
	"ind": "India",
	"iot": "British Indian Ocean Territory",
	"irl": "Ireland",
	"irn": "Iran",
	"irq": "Iraq",
	"isl": "Iceland",
	"isr": "Israel",
	"ita": "Italy",
	"jam": "Jamaica",
	"jey": "Jersey",
	"jor": "Jordan",
	"jpn": "Japan",
	"kaz": "Kazakhstan",
	"ken": "Kenya",
	"kgz": "Kyrgyzstan",
	"khm": "Cambodia",
	"kir": "Kiribati",
	"kna": "Saint Kitts and Nevis",
	"kor": "Korea South",
	"kwt": "Kuwait",
	"lao": "Laos",
	"lbn": "Lebanon",
	"lbr": "Liberia",
	"lby": "Libya",
	"lca": "Saint Lucia",
	"lie": "Liechtenstein",
	"lka": "Sri Lanka",
	"lso": "Lesotho",
	"ltu": "Lithuania",
	"lux": "Luxembourg",
	"lva": "Latvia",
	"mac": "Macao",
	"maf": "Saint Martin",
	"mar": "Morocco",
	"mco": "Monaco",
	"mda": "Moldova",
	"mdg": "Madagascar",
	"mdv": "Maldives",
	"mex": "Mexico",
	"mhl": "Marshall Islands",
	"mkd": "Macedonia",
	"mli": "Mali",
	"mlt": "Malta",
	"mmr": "Myanmar",
	"mne": "Montenegro",
	"mng": "Mongolia",
	"mnp": "Northern Mariana Islands",
	"moz": "Mozambique",
	"mrt": "Mauritania",
	"msr": "Montserrat",
	"mus": "Mauritius",
	"mwi": "Malawi",
	"mys": "Malaysia",
	"myt": "Mayotte",
	"nam": "Namibia",
	"ncl": "New Caledonia",
	"ner": "Niger",
	"nfk": "Norfolk Island",
	"nga": "Nigeria",
	"nic": "Nicaragua",
	"niu": "Niue",
	"nld": "Netherlands",
	"nor": "Norway",
	"npl": "Nepal",
	"nru": "Nauru",
	"nzl": "New Zealand",
	"omn": "Oman",
	"pak": "Pakistan",
	"pan": "Panama",
	"pcn": "Pitcairn",
	"per": "Peru",
	"phl": "Philippines",
	"plw": "Palau",
	"png": "Papua New Guinea",
	"pol": "Poland",
	"pri": "Puerto Rico",
	"prk": "Korea North",
	"prt": "Portugal",
	"pry": "Paraguay",
	"pse": "Palestinian Territory",
	"pyf": "French Polynesia",
	"qat": "Qatar",
	"rou": "Romania",
	"rus": "Russia",
	"rwa": "Rwanda",
	"sau": "Saudi Arabia",
	"sdn": "Sudan",
	"sen": "Senegal",
	"sgp": "Singapore",
	"shn": "Saint Helena Ascension and Tristan da Cunha",
	"sjm": "Svalbard",
	"slb": "Solomon Islands",
	"sle": "Sierra Leone",
	"slv": "El Salvador",
	"smr": "San Marino",
	"som": "Somalia",
	"spm": "Saint Pierre and Miquelon",
	"srb": "Serbia",
	"stp": "Sao Tome and Principe",
	"sur": "Suriname",
	"svk": "Slovakia",
	"svn": "Slovenia",
	"swe": "Sweden",
	"swz": "Swaziland",
	"syc": "Seychelles",
	"syr": "Syria",
	"tca": "Turks and Caicos Islands",
	"tcd": "Chad",
	"tgo": "Togo",
	"tha": "Thailand",
	"tjk": "Tajikistan",
	"tkl": "Tokelau",
	"tkm": "Turkmenistan",
	"tls": "Timor-Leste",
	"ton": "Tonga",
	"tto": "Trinidad and Tobago",
	"tun": "Tunisia",
	"tur": "Turkey",
	"tuv": "Tuvalu",
	"twn": "Taiwan",
	"tza": "Tanzania",
	"uga": "Uganda",
	"ukr": "Ukraine",
	"ury": "Uruguay",
	"usa": "United States",
	"uzb": "Uzbekistan",
	"vat": "Holy See",
	"vct": "Saint Vincent and the Grenadines",
	"ven": "Venezuela",
	"vgb": "British Virgin Islands",
	"vir": "Virgin Islands",
	"vnm": "Vietnam",
	"vut": "Vanuatu",
	"wlf": "Wallis and Futuna",
	"wsm": "Samoa",
	"yem": "Yemen",
	"zaf": "South Africa",
	"zmb": "Zambia",
	"zwe": "Zimbabwe"
}

ISO2CODES = {
	"aw": "Aruba",
	"af": "Afghanistan",
	"ao": "Angola",
	"ai": "Anguilla",
	"al": "Albania",
	"ad": "Andorra",
	"an": "Netherlands Antilles",
	"ae": "United Arab Emirates",
	"ar": "Argentina",
	"am": "Armenia",
	"as": "American Samoa",
	"aq": "Antarctica",
	"tf": "French Southern Territories",
	"ag": "Antigua and Barbuda",
	"au": "Australia",
	"at": "Austria",
	"az": "Azerbaijan",
	"bi": "Burundi",
	"be": "Belgium",
	"bj": "Benin",
	"bf": "Burkina Faso",
	"bd": "Bangladesh",
	"bg": "Bulgaria",
	"bh": "Bahrain",
	"bs": "Bahamas",
	"ba": "Bosnia and Herzegovina",
	"bl": "Saint Barthelemy",
	"by": "Belarus",
	"bz": "Belize",
	"bm": "Bermuda",
	"bo": "Bolivia",
	"br": "Brazil",
	"bb": "Barbados",
	"bn": "Brunei",
	"bt": "Bhutan",
	"bv": "Bouvet Island",
	"bw": "Botswana",
	"cf": "Central African Republic",
	"ca": "Canada",
	"cc": "Cocos Islands",
	"ch": "Switzerland",
	"cl": "Chile",
	"cn": "China",
	"ci": "Ivory Coast",
	"cm": "Cameroon",
	"cd": "Congo Democratic Republic",
	"cg": "Congo Republic",
	"ck": "Cook Islands",
	"co": "Colombia",
	"km": "Comoros",
	"cv": "Cape Verde",
	"cr": "Costa Rica",
	"cu": "Cuba",
	"cx": "Christmas Island",
	"ky": "Cayman Islands",
	"cy": "Cyprus",
	"cz": "Czech Republic",
	"de": "Germany",
	"dj": "Djibouti",
	"dm": "Dominica",
	"dk": "Denmark",
	"do": "Dominican Republic",
	"dz": "Algeria",
	"ec": "Ecuador",
	"eg": "Egypt",
	"er": "Eritrea",
	"eh": "Western Sahara",
	"es": "Spain",
	"ee": "Estonia",
	"et": "Ethiopia",
	"fi": "Finland",
	"fj": "Fiji",
	"fk": "Falkland Islands",
	"fr": "France",
	"fo": "Faroe Islands",
	"fm": "Micronesia",
	"ga": "Gabon",
	"gb": "United Kingdom",
	"ge": "Georgia",
	"gg": "Guernsey",
	"gh": "Ghana",
	"gi": "Gibraltar",
	"gn": "Guinea",
	"gm": "Gambia",
	"gw": "Guinea-Bissau",
	"gq": "Equatorial Guinea",
	"gr": "Greece",
	"gd": "Grenada",
	"gl": "Greenland",
	"gt": "Guatemala",
	"gu": "Guam",
	"gy": "Guyana",
	"hk": "Hong Kong",
	"hm": "Heard Island and McDonald Islands",
	"hn": "Honduras",
	"hr": "Croatia",
	"ht": "Haiti",
	"hu": "Hungary",
	"id": "Indonesia",
	"im": "Isle of Man",
	"in": "India",
	"io": "British Indian Ocean Territory",
	"ie": "Ireland",
	"ir": "Iran",
	"iq": "Iraq",
	"is": "Iceland",
	"il": "Israel",
	"it": "Italy",
	"jm": "Jamaica",
	"je": "Jersey",
	"jo": "Jordan",
	"jp": "Japan",
	"kz": "Kazakhstan",
	"ke": "Kenya",
	"kg": "Kyrgyzstan",
	"kh": "Cambodia",
	"ki": "Kiribati",
	"kn": "Saint Kitts and Nevis",
	"kr": "Korea South",
	"kw": "Kuwait",
	"la": "Laos",
	"lb": "Lebanon",
	"lr": "Liberia",
	"ly": "Libya",
	"lc": "Saint Lucia",
	"li": "Liechtenstein",
	"lk": "Sri Lanka",
	"ls": "Lesotho",
	"lt": "Lithuania",
	"lu": "Luxembourg",
	"lv": "Latvia",
	"mo": "Macao",
	"mf": "Saint Martin",
	"ma": "Morocco",
	"mc": "Monaco",
	"md": "Moldova",
	"mg": "Madagascar",
	"mv": "Maldives",
	"mx": "Mexico",
	"mh": "Marshall Islands",
	"mk": "Macedonia",
	"ml": "Mali",
	"mt": "Malta",
	"mm": "Myanmar",
	"me": "Montenegro",
	"mn": "Mongolia",
	"mp": "Northern Mariana Islands",
	"mz": "Mozambique",
	"mr": "Mauritania",
	"ms": "Montserrat",
	"mu": "Mauritius",
	"mw": "Malawi",
	"my": "Malaysia",
	"yt": "Mayotte",
	"na": "Namibia",
	"nc": "New Caledonia",
	"ne": "Niger",
	"nf": "Norfolk Island",
	"ng": "Nigeria",
	"ni": "Nicaragua",
	"nu": "Niue",
	"nl": "Netherlands",
	"no": "Norway",
	"np": "Nepal",
	"nr": "Nauru",
	"nz": "New Zealand",
	"om": "Oman",
	"pk": "Pakistan",
	"pa": "Panama",
	"pn": "Pitcairn",
	"pe": "Peru",
	"ph": "Philippines",
	"pw": "Palau",
	"pg": "Papua New Guinea",
	"pl": "Poland",
	"pr": "Puerto Rico",
	"kp": "Korea North",
	"pt": "Portugal",
	"py": "Paraguay",
	"ps": "Palestinian Territory",
	"pf": "French Polynesia",
	"qa": "Qatar",
	"ro": "Romania",
	"ru": "Russia",
	"rw": "Rwanda",
	"sa": "Saudi Arabia",
	"sd": "Sudan",
	"sn": "Senegal",
	"sg": "Singapore",
	"sh": "Saint Helena Ascension and Tristan da Cunha",
	"sj": "Svalbard",
	"sb": "Solomon Islands",
	"sl": "Sierra Leone",
	"sv": "El Salvador",
	"sm": "San Marino",
	"so": "Somalia",
	"pm": "Saint Pierre and Miquelon",
	"rs": "Serbia",
	"st": "Sao Tome and Principe",
	"sr": "Suriname",
	"sk": "Slovakia",
	"si": "Slovenia",
	"se": "Sweden",
	"sz": "Swaziland",
	"sc": "Seychelles",
	"sy": "Syria",
	"tc": "Turks and Caicos Islands",
	"td": "Chad",
	"tg": "Togo",
	"th": "Thailand",
	"tj": "Tajikistan",
	"tk": "Tokelau",
	"tm": "Turkmenistan",
	"tl": "Timor-Leste",
	"to": "Tonga",
	"tt": "Trinidad and Tobago",
	"tn": "Tunisia",
	"tr": "Turkey",
	"tv": "Tuvalu",
	"tw": "Taiwan",
	"tz": "Tanzania",
	"ug": "Uganda",
	"ua": "Ukraine",
	"uy": "Uruguay",
	"us": "United States",
	"uz": "Uzbekistan",
	"va": "Holy See",
	"vc": "Saint Vincent and the Grenadines",
	"ve": "Venezuela",
	"vg": "British Virgin Islands",
	"vi": "Virgin Islands",
	"vn": "Vietnam",
	"vu": "Vanuatu",
	"wf": "Wallis and Futuna",
	"ws": "Samoa",
	"ye": "Yemen",
	"za": "South Africa",
	"zm": "Zambia",
	"zw": "Zimbabwe"
}

ISO2TOISO3 = {  # Convert iso2 to iso3 codes
	'yem': 'ye',
	'bvt': 'bv',
	'mnp': 'mp',
	'lso': 'ls',
	'uga': 'ug',
	'tkm': 'tm',
	'alb': 'al',
	'ita': 'it',
	'tto': 'tt',
	'nld': 'nl',
	'moz': 'mz',
	'tcd': 'td',
	'blr': 'by',
	'mne': 'me',
	'mng': 'mn',
	'bfa': 'bf',
	'nga': 'ng',
	'zmb': 'zm',
	'gmb': 'gm',
	'hrv': 'hr',
	'gtm': 'gt',
	'lka': 'lk',
	'aus': 'au',
	'jam': 'jm',
	'pcn': 'pn',
	'aut': 'at',
	'ven': 've',
	'vct': 'vc',
	'mwi': 'mw',
	'fin': 'fi',
	'tkl': 'tk',
	'rwa': 'rw',
	'ant': 'an',
	'bih': 'ba',
	'cpv': 'cv',
	'tjk': 'tj',
	'pse': 'ps',
	'lca': 'lc',
	'geo': 'ge',
	'atf': 'tf',
	'nor': 'no',
	'mhl': 'mh',
	'png': 'pg',
	'wsm': 'ws',
	'zwe': 'zw',
	'gum': 'gu',
	'gbr': 'gb',
	'civ': 'ci',
	'guy': 'gy',
	'cri': 'cr',
	'cmr': 'cm',
	'shn': 'sh',
	'lie': 'li',
	'nfk': 'nf',
	'mda': 'md',
	'mdg': 'mg',
	'hti': 'ht',
	'aze': 'az',
	'lao': 'la',
	'are': 'ae',
	'chn': 'cn',
	'arg': 'ar',
	'sen': 'sn',
	'btn': 'bt',
	'mdv': 'mv',
	'arm': 'am',
	'est': 'ee',
	'mus': 'mu',
	'blz': 'bz',
	'lux': 'lu',
	'irq': 'iq',
	'bdi': 'bi',
	'smr': 'sm',
	'per': 'pe',
	'brb': 'bb',
	'blm': 'bl',
	'irl': 'ie',
	'sur': 'sr',
	'irn': 'ir',
	'abw': 'aw',
	'lva': 'lv',
	'tca': 'tc',
	'ner': 'ne',
	'esh': 'eh',
	'plw': 'pw',
	'ken': 'ke',
	'jor': 'jo',
	'tur': 'tr',
	'ggy': 'gg',
	'omn': 'om',
	'tuv': 'tv',
	'mmr': 'mm',
	'bwa': 'bw',
	'ecu': 'ec',
	'tun': 'tn',
	'swe': 'se',
	'rus': 'ru',
	'mex': 'mx',
	'asm': 'as',
	'tls': 'tl',
	'atg': 'ag',
	'bgd': 'bd',
	'ltu': 'lt',
	'ata': 'aq',
	'isr': 'il',
	'caf': 'cf',
	'idn': 'id',
	'vut': 'vu',
	'bol': 'bo',
	'cod': 'cd',
	'cog': 'cg',
	'sjm': 'sj',
	'eth': 'et',
	'com': 'km',
	'col': 'co',
	'wlf': 'wf',
	'cxr': 'cx',
	'ago': 'ao',
	'zaf': 'za',
	'sgp': 'sg',
	'som': 'so',
	'uzb': 'uz',
	'isl': 'is',
	'vir': 'vi',
	'brn': 'bn',
	'pol': 'pl',
	'kwt': 'kw',
	'imn': 'im',
	'tgo': 'tg',
	'bra': 'br',
	'fra': 'fr',
	'mkd': 'mk',
	'che': 'ch',
	'usa': 'us',
	'jey': 'je',
	'fro': 'fo',
	'msr': 'ms',
	'dnk': 'dk',
	'hkg': 'hk',
	'swz': 'sz',
	'ton': 'to',
	'gib': 'gi',
	'gin': 'gn',
	'kor': 'kr',
	'vat': 'va',
	'cub': 'cu',
	'mco': 'mc',
	'dza': 'dz',
	'cyp': 'cy',
	'hun': 'hu',
	'kgz': 'kg',
	'fji': 'fj',
	'dji': 'dj',
	'ncl': 'nc',
	'bmu': 'bm',
	'hmd': 'hm',
	'sdn': 'sd',
	'gab': 'ga',
	'nru': 'nr',
	'hnd': 'hn',
	'dma': 'dm',
	'gnq': 'gq',
	'ben': 'bj',
	'bel': 'be',
	'slv': 'sv',
	'mli': 'ml',
	'deu': 'de',
	'gnb': 'gw',
	'flk': 'fk',
	'stp': 'st',
	'can': 'ca',
	'mlt': 'mt',
	'rou': 'ro',
	'sle': 'sl',
	'aia': 'ai',
	'eri': 'er',
	'slb': 'sb',
	'nzl': 'nz',
	'and': 'ad',
	'lbr': 'lr',
	'jpn': 'jp',
	'lby': 'ly',
	'mys': 'my',
	'pri': 'pr',
	'myt': 'yt',
	'prk': 'kp',
	'tza': 'tz',
	'prt': 'pt',
	'spm': 'pm',
	'ind': 'in',
	'bhs': 'bs',
	'bhr': 'bh',
	'pry': 'py',
	'sau': 'sa',
	'cze': 'cz',
	'qat': 'qa',
	'ukr': 'ua',
	'cym': 'ky',
	'afg': 'af',
	'bgr': 'bg',
	'vgb': 'vg',
	'nam': 'na',
	'grd': 'gd',
	'grc': 'gr',
	'twn': 'tw',
	'khm': 'kh',
	'grl': 'gl',
	'pak': 'pk',
	'srb': 'rs',
	'pan': 'pa',
	'syc': 'sc',
	'npl': 'np',
	'kir': 'ki',
	'mar': 'ma',
	'lbn': 'lb',
	'phl': 'ph',
	'nic': 'ni',
	'vnm': 'vn',
	'iot': 'io',
	'syr': 'sy',
	'mac': 'mo',
	'maf': 'mf',
	'kaz': 'kz',
	'cok': 'ck',
	'pyf': 'pf',
	'niu': 'nu',
	'svn': 'si',
	'egy': 'eg',
	'svk': 'sk',
	'dom': 'do',
	'mrt': 'mr',
	'esp': 'es',
	'fsm': 'fm',
	'kna': 'kn',
	'gha': 'gh',
	'cck': 'cc',
	'chl': 'cl',
	'ury': 'uy',
	'tha': 'th'
}


class selectCountryBone(selectBone):
	ISO2 = 2
	ISO3 = 3

	def __init__(self, codes=ISO2, *args, **kwargs):
		global ISO2CODES, ISO3CODES
		super(selectBone, self).__init__(*args, **kwargs)

		assert codes in [self.ISO2, self.ISO3]

		if codes == self.ISO2:
			self.values = OrderedDict(sorted(ISO2CODES.items(), key=lambda i: i[1]))
		else:
			self.values = OrderedDict(sorted(ISO3CODES.items(), key=lambda i: i[1]))

		self.codes = codes

	def unserialize(self, valuesCache, name, expando):
		if name in expando:
			value = expando[name]
			if isinstance(value, str) and len(
					value) == 3 and self.codes == self.ISO2:  # We got an ISO3 code from the db, but are using ISO2
				try:
					valuesCache[name] = ISO2TOISO3[value]
				except:
					pass
			elif isinstance(value, str) and len(
					value) == 2 and self.codes == self.ISO3:  # We got ISO2 code, wanted ISO3
				inv = {v: k for k, v in ISO2TOISO3.items()}  # Inverted map
				try:
					valuesCache[name] = inv[value]
				except:
					pass
			else:
				if value in self.values:
					valuesCache[name] = value
		return (True)

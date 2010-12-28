#
# Plex Movie Metadata Agent using Ciné-passion database (French communauty)
# V1.5 By oncleben31 (http://oncleben31.cc) - 2010
# 

#TODO: Essayer de fair une Agent secondaire pour IMDB juste pour retrouver les informations de type text
#TODO: ajouter prise en charge des sous titre.


import datetime, unicodedata, re, urllib2

CP_API_KEY = '38ca89564b2259401518960f7a06f94b/'
# WARNING : If you want to use the Ciné-Passion DDB for your project, don't use this key but 
# ask a free one on this page : http://passion-xbmc.org/demande-clef-api-api-key-request/

CP_API_URL = 'http://passion-xbmc.org/scraper/API/1/'
CP_API_SEARCH = 'Movie.Search/Title/%s/XML/'
CP_API_INFO = 'Movie.GetInfo/ID/%s/XML/'

GOOGLE_JSON_URL = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=large&q=%s'
BING_JSON_URL   = 'http://api.bing.net/json.aspx?AppId=BAFE92EAA23CD237BCDAA5AB39137036739F7357&Version=2.2&Query=%s&Sources=web&Web.Count=8&JsonType=raw'

CP_COEFF_YEAR = 3
CP_COEFF_TITLE = 2
CP_DATE_PENALITY = 25
CP_RESULT_POS_PENALITY = 1

CP_CACHETIME_CP_SEARCH = CACHE_1DAY
CP_CACHETIME_CP_FANART = CACHE_1MONTH


def Start():
  HTTP.CacheTime = CACHE_1DAY
  Log("[cine-passion Agent] : Version 1.5")

	

class CinepassionAgent(Agent.Movies):
  name = 'Ciné-Passion'
  languages = ['fr', 'en']
  accepts_from = ['com.plexapp.agents.localmedia', 'com.plexapp.agents.opensubtitles']
  
  def search(self, results, media, lang):
	
	#temporary special case for Disney's
	try: 
		m = re.match('N° [0-9]* ([0-9]*) Walt Disney (.*)$', media.name)
		if m:
		  new_name, new_yearString = (m.group(2), m.group(1))
		  Log('[cine-passion Agent] : DEBUG new_name : ' + new_name + ' | new_year : ' + new_yearString)
		  media.name = new_name
		  media.year = new_yearString
	except:
		Log("[cine-passion Agent] : Ciné-Passion Agent has return an error when managing the Disney Case.")
		
  	#Launch search on media name using name without accents.
	searchURL = CP_API_URL + CP_API_SEARCH % lang + CP_API_KEY + String.Quote(self.stripAccents(media.name.encode('utf-8')), usePlus = True)
	
	try:
		searchXMLresult = XML.ElementFromURL(searchURL, cacheTime=CP_CACHETIME_CP_SEARCH)
	
		#Test if DDB have return an error
		hasError = self.checkErrors(searchXMLresult, media.name.encode('utf-8'))
		
	except Ex.HTTPError, e:
		Log("[cine-passion Agent] : Code HTTP de retour différent de 200 : "+ e)
	except Exception, e :
		Log("[cine-passion Agent] : EXCEPT1 " + str(e))
		hasError = True
		Log("[cine-passion Agent] : Ciné-Passion Agent has return an unkown error wile retrieving search result for '" + media.name.encode('utf-8') +"'")
	
	if (hasError ==  False) :
		#Analyse the results
		self.scrapeXMLsearch(results, media, lang, searchXMLresult, skipCinePassion = False)
	else:
		#Analyse the results just with Google
		self.scrapeXMLsearch(results, media, lang, None, skipCinePassion = True)



  def update(self, metadata, media, lang):
	
	try:
		#Ask for movie information
		# Cache management to avoid consuming Ciné-Passion database quotas (about 300 per day)
		pref_cache = Prefs["pref_cache"]
		if pref_cache == "1 jour/day" :
			CP_CACHETIME_CP_REQUEST = CACHE_1DAY
		elif pref_cache == "1 semaine/week":
			CP_CACHETIME_CP_REQUEST = CACHE_1WEEK
		elif pref_cache == "1 mois/month":
			CP_CACHETIME_CP_REQUEST = CACHE_1MONTH
		Log('[cine-passion Agent] : requesting movie with ID "' + metadata.id + '" with cache time set to : ' + str(CP_CACHETIME_CP_REQUEST))
		updateXMLresult = XML.ElementFromURL(CP_API_URL + CP_API_INFO % lang + CP_API_KEY + metadata.id, cacheTime=CP_CACHETIME_CP_REQUEST)
	
		#Test if DDB have return an error
		hasError = self.checkErrors(updateXMLresult, metadata.title)
	except Ex.HTTPError, e:
		Log("[cine-passion Agent] : Code HTTP de retour différent de 200 : "+ e)
	except Exception, e :
		Log("[cine-passion Agent] : EXCEPT2 " + str(e))
		hasError = True
		if metadata.title != None :
			Log("[cine-passion Agent] ERROR : Agent has return an unkown error wile retrieving information for '" + metadata.title +"'")
		else :
			Log("[cine-passion Agent] ERROR : Agent has return an unkown error wile retrieving information for ID'" + metadata.id +"'")
			
	if (hasError == False) :
		#genre
		metadata.genres.clear()
		for genre in updateXMLresult.findall('genres/genre'):
			metadata.genres.add(genre.text)
	
		#director
		metadata.directors.clear()
		for director in updateXMLresult.findall('directors/director'):
			metadata.directors.add(director.text)

		#writers
		metadata.writers.clear()
		for writer in updateXMLresult.findall('credits/credit'):
			metadata.writers.add(writer.text)	

		#studios
		# Just the first one is taken. Plex didn't manage more than one
		metadata.studio = updateXMLresult.find('studios/studio').text 
		
		#runtime
		runtime = int(updateXMLresult.find('runtime').text) * 60 * 1000           
		
		year = updateXMLresult.find('year').text
		if year != "":
			metadata.year = int(year)             
	
		#originally_available_at
		metadata.originally_available_at = Datetime.ParseDate(year).date()
		
		#Original title.
		originalTitle = updateXMLresult.find('originaltitle').text
		metadata.original_title = originalTitle
		
		#title
		metadata.title = updateXMLresult.find('title').text.replace('&#39;','\'') # Patch to suppress some HTML code in title.
		
		#metadata.tagline = updateXMLresult.find('tagline').text  
		#tagline tag ignored since there are not real tagline in Ciné-passion DDB
				
		metadata.summary = updateXMLresult.find('plot').text
	
		#Posters and arts
		@parallelize
		def LoopForArtsFetching():
			posters_valid_names = list()
			art_valid_names = list()
			
			images = updateXMLresult.findall("images/image[@size='preview']")
			indexImages = 1
			for image in images:
				@task
				def grapArts(metadata = metadata, image = image, indexImages = indexImages):
					thumbUrl = image.get('url')
					url = thumbUrl.replace("/preview/", "/main/")
				
					type = image.get('type')
					if (type == 'Poster'):
						try:
							#Check if main image exist
							f = urllib2.urlopen(url)
							test = f.info().gettype()
							
							metadata.posters[url] = Proxy.Preview(HTTP.Request(thumbUrl, cacheTime=CP_CACHETIME_CP_FANART), sort_order = indexImages)
							posters_valid_names.append(url)
						except	Exception, e :
							Log("[cine-passion Agent] : EXCEPT3 " + str(e))
							Log('[cine-passion Agent] Error when fetching ' + thumbUrl + ' or '+ url)
					elif (type == 'Fanart'):
						try:
							#Check if main image exist
							f = urllib2.urlopen(url)
							test = f.info().gettype()
							
							metadata.art[url] = Proxy.Preview(HTTP.Request(thumbUrl, cacheTime=CP_CACHETIME_CP_FANART), sort_order = indexImages)
							art_valid_names.append(url)
						except	Exception, e :
							Log("[cine-passion Agent] : EXCEPT4 " + str(e))
							Log('[cine-passion Agent] Error when fetching ' + thumbUrl + ' or '+ url)
				indexImages = indexImages + 1
			
			#supress old unsued pictures
			metadata.posters.validate_keys(posters_valid_names)
			metadata.art.validate_keys(art_valid_names)
			
		#Rating source selection done by pref pane.
		rating_source = Prefs["pref_rating_source"]
		metadata.rating = float(updateXMLresult.find("ratings/rating[@type='" + rating_source + "']").text.replace(',','.'))
	
		#roles              
		metadata.roles.clear()
		for person in updateXMLresult.findall('casting/person'):
			role = metadata.roles.new()
			role.role = person.get('character')
			role.actor = person.get('name')
			role.photo = person.get('thumb')
			Log('[cine-passion Agent] Ajout d un personnage : ' + role.role + ' (' + role.actor + ')')
	
		#content_rating - Ciné-Passion manage France and USA ratings.
		content_rating_source = Prefs["pref_content_rating"]
		CP_content_rating = updateXMLresult.find("certifications/certification[@nation='" + content_rating_source + "']")
		if CP_content_rating == None :
			Log('[cine-passion Agent] : content rating ('+ content_rating_source + ') not found for ' + metadata.title +' ('+ metadata.id +')')
		else :
			if content_rating_source == "France" :
				metadata.content_rating = 'fr/' + CP_content_rating.text
			else :
				metadata.content_rating = CP_content_rating.text
			Log('[cine-passion Agent] : content rating ('+ content_rating_source + ') is "'+ metadata.content_rating +'" for ' + metadata.title +' ('+ metadata.id +')')
		
		#collection
		Log('[cine-passion Agent] : pref_ignore_collection  is "'+ str(Prefs["pref_ignore_collection"]) +'"')
		metadata.collections.clear()
		if Prefs["pref_ignore_collection"] == False:
			if updateXMLresult.find('saga').text != None :
				metadata.collections.add(updateXMLresult.find('saga').text)
		
		### Tags not used   
		#first_released : not in DDB    
		#tags : not in DDB              
		#trivia : not used       
		#quotes : not in DDB             
		#banners : not in DDB           
		#themes : not in DDB             
	
	

  def scrapeXMLsearch(self, results, media, lang, XMLresult, skipCinePassion):
	
		
	# initialise score
	score = 99
	
	# Search in Ciné-Passion DDB
	if skipCinePassion == False:
		# For any <movie> tag in XML response
		for movie in XMLresult.xpath("//movie"):
			#find movie information (id, title and year)
			id = movie.find('id').text
			name = movie.find('title').text.replace('&#39;','\'').replace('&#338;', 'Œ').replace('&amp;#338;', 'Œ') # Patch to suppress some HTML code in title.
			originalName = movie.find('originaltitle').text
			year = int(movie.find('year').text) 
			lang = lang
		
			finalScore = score - self.scoreResultPenalty(media, year, name, originalName)
			#The movie information are added to the result
			results.Append(MetadataSearchResult(id =id, name=name, year=year, lang=lang, score=finalScore))
			
			# First results should be more acruate.
			score = score - 1
	
	# Search on Google and BING to get Allociné ID (Big Thanks to IMDB Agent :-)
	if media.year:
	  searchYear = ' (' + str(media.year) + ')'
	else:
	  searchYear = ''

	normalizedName = self.stripAccents(media.name)
	GOOGLE_JSON_QUOTES = GOOGLE_JSON_URL % String.Quote('"' + normalizedName + searchYear + '"', usePlus=True) + '+site:allocine.fr/film/fichefilm_gen_cfilm'
	GOOGLE_JSON_NOQUOTES = GOOGLE_JSON_URL % String.Quote(normalizedName + searchYear, usePlus=True) + '+site:allocine.fr/film/fichefilm_gen_cfilm'
	BING_JSON = BING_JSON_URL % String.Quote(normalizedName + searchYear, usePlus=True) + '+site:allocine.fr/film'
	
	#Reinit classment score since CinePassion can shift good movies.
	score = 99
	
	for s in [GOOGLE_JSON_QUOTES, GOOGLE_JSON_NOQUOTES, BING_JSON]:
	
		hasResults = False
		try:
			if s.count('bing.net') > 0:
				jsonObj = JSON.ObjectFromURL(s)['SearchResponse']['Web']
				if jsonObj['Total'] > 0:
					jsonObj = jsonObj['Results']
					hasResults = True
					urlKey = 'Url'
					titleKey = 'Title'
			elif s.count('googleapis.com') > 0:
				jsonObj = JSON.ObjectFromURL(s)
				if jsonObj['responseData'] != None:
					jsonObj = jsonObj['responseData']['results']
					if len(jsonObj) > 0:
						hasResults = True
						urlKey = 'unescapedUrl'
						titleKey = 'title'
		except Exception, e :
			Log("[cine-passion Agent] : EXCEPT5 " + str(e))
			Log('[cine-passion Agent] Error when fetching ' + s)
		
		if hasResults :
			goodItem = 0
			for item in jsonObj:
				#Stop parsing search engin results after 3 matching.
				if goodItem > 3:
					continue
				
				url = item[urlKey]
				title = self.stripHTMLTags(item[titleKey])
				
				try: 
					m = re.match('(.*)[ ]+\(([12][0-9]{3})(/[A-Z]+)?\).*$', title)
					if m:
					  name,yearString = (m.group(1), m.group(2))
					  year = int(yearString)
					else:
					  year = None
							
					m = re.match('http://www.allocine.fr/film/fichefilm_gen_cfilm=([0-9]*).html', url)
					if m:
						id = m.group(1)
		  			else:
						#If no id the results is not on allocine. skip it
						continue
						
					# No way to find original name so name is used two times.
					finalScore = score - self.scoreResultPenalty(media, year, name, name)
					results.Append(MetadataSearchResult(id =id, name=name, year=year, lang=lang, score=finalScore))
					
					# First results should be more acruate.
					score = score - CP_RESULT_POS_PENALITY
					goodItem = goodItem + 1
			
				except Exception, e :
					Log("[cine-passion Agent] : EXCEPT6 " + str(e))
					Log('[cine-passion Agent] Error when parsing ' + url)
		
			Log('trouvé '+ str(goodItem-1))
		
    
	# Finally, remove duplicate entries.
	results.Sort('score', descending=True)
	toWhack = []
	resultMap = {}
	for result in results:
	  if not resultMap.has_key(result.id):
	    resultMap[result.id] = True
	  else:
	    toWhack.append(result)
	
	for dupe in toWhack:
	  results.Remove(dupe)
	
	# Just for Log
	for result in results:
		Log('scraped results: ' + result.name + ' | year = ' + str(result.year) + ' | id = ' + result.id + '| score = ' + str(result.score))
				
		
  def checkQuota(self, XMLresult):
	# This function check the quota of the Cine-passion DDB
	# For now just a Log in console. In the futur a popup warning to alert the user should be better
	try:
		hasError = False
		quota = XMLresult.find('quota')
		if quota != None:
			used = quota.get('use')
			authorized =  quota.get('authorize')
			resetDate = quota.get('reset_date')
			Log('Quota : used: ' + used + " on "+ authorized + " | reset date: "+ resetDate)
		
		tagID = XMLresult.find('movie/id')
		#Double check because root element is different when quota reach.
		if tagID != None:
			if tagID.text == "-1":			
				Log('WARNING: Quota reached, no more result before reset.')
				hasError = True
		
	except	Exception , e:
		Log("[cine-passion Agent] : DEBUG EXCEPT7" + str(e))
		hasError = True
		
	return hasError
	
  def checkErrors(self, XMLresult, name):
	# This function check if the Ciné-passion have return an error
	try:
		hasError = False
		for i in XMLresult.findall('error'):
			Log("ERROR : Ciné-Passion API return the error when searching for '"+ name+ "': "+ i.text)
			hasError = True
		
		if hasError == False:
			#Verification du quotas
			hasError = self.checkQuota(XMLresult)
			
	except Exception , e:
		Log("[cine-passion Agent] : EXCEPT8" + str(e))
		hasError = True
	
	return hasError

  def stripAccents(self, str):
    nkfd_form = unicodedata.normalize('NFKD', unicode(str))
    only_ascii = nkfd_form.encode('ASCII', 'ignore')
    return only_ascii

  def stripHTMLTags(self, str):
	p = re.compile(r'<.*?>')
	return p.sub('', str)
	
  def scoreResultPenalty(self, media, year, name, originalName):
	# Penality if date is in futur
	# Penality proportional to distance between dates if available
	# Penality proportional to the Levenshtein distance between title. min of distance calculate for title and originalTitle is used.
	
	#Control to evaluate the result.
	scorePenalty = 0
	if year > datetime.datetime.now().year:
		scorePenalty = CP_DATE_PENALITY
	
	#If there is a date in the video file name compute the difference
	if media.year:
		scorePenalty = scorePenalty + abs(year - int(media.year)) * CP_COEFF_YEAR

	#Use String distance as penalty. Use accents 
	#nameDist = Util.LevenshteinDistance(self.stripAccents(media.name.lower()), self.stripAccents(name.lower()))
	#originalNameDist = Util.LevenshteinDistance(self.stripAccents(media.name.lower()), self.stripAccents(originalName.lower()))
	nameDist = Util.LevenshteinDistance(media.name.lower(), name.lower())
	originalNameDist = Util.LevenshteinDistance(media.name.lower(), originalName.lower())
	minDist = min(nameDist, originalNameDist)
	scorePenalty = scorePenalty + minDist * CP_COEFF_TITLE


	return scorePenalty
	
import json
import re
import sys

def main(diagnostic=False):
    global members
    print 'raw members: ', len(members)

    #First, label adults and children with ID's
    for i,member in enumerate(members):
        parseAdultChild(member)
        
    #Now go back through, starting with roots w/no parents,
    #and build the trees
    fullFamilies = []
    for member in members:
        if 'parentID' not in member:
            if diagnostic:
                fullFamilies.append(buildTree(member))
            else:
                try:
                    fullFamilies.append(buildTree(member))
                except:# RuntimeError, AssertionError, 
                    e = sys.exc_info()[0]
                    print "Error: {}, {}".format(member['last'],member['first'])
                    print e
    print 'number of families:', len(fullFamilies)
    with open('data/members.json','w') as f:
        f.write(json.dumps(fullFamilies))


def parseHeadLine(line,memberID):
    '''
    Split the first line of the directory entry into:
    houseNum, last,first, nickname, and spouse
    '''
    #Split that first line on \t.
    #First element is name, last element is House number
    firstLine = line.strip().split('\t')
    fullNames = firstLine[0].strip()
    member = {}
    member['house'] = firstLine[-1].strip()
    member['id'] = memberID
    if ')' in line:
        parents = line.split(')')[0].split('(')
        head = parents[0]
        if ',' in parents[1]:
            #if spouse, add spouse
            member['nickname'] = parents[1].split(',')[0].strip()
            member['spouse'] = ','.join(parents[1].split(',')[1:]).strip()
        else:
            member['nickname'] = parents[1].strip()
    else:
        head = line
        nickname = None
        spouse = None
    lastName = head.split(',')[0]
    firstName = ','.join(head.split(',')[1:])
    member['last'] = lastName.strip()
    member['first'] = firstName.strip()
    return member


def findFirstChildLine(lines):
    '''
    Identify the first line for the list of children
    '''
    phonePattern = re.compile(r'(\d{3})-(\d{4})')
    emailPattern = re.compile(r'[^@]+@[^@]+\.[^@]+')
    lastPhoneLine = 0
    lastEmailLine = 0
    for i,line in enumerate(lines):
        if phonePattern.search(line):
            lastPhoneLine = i
        if emailPattern.search(line):
            lastEmailLine = i
    firstChildLine = max(lastPhoneLine,lastEmailLine)+1
    return firstChildLine


def getLastName(stepGroup,parentLast):
    '''
    split on commas
    remove anything inside parentheses
    remove q.v.
    split on space. 
    candidates are either the last one, two, or three space-separated words
    if no last name, use parent last name
    stepGroup:
        string of child names from one of the marriages
    parentLast:
        last name of head of household parent
    '''
    stepGroup = re.sub("([\(]).*?([\)])", "\g<1>\g<2>", stepGroup)
    stepGroup = stepGroup.replace('(','').replace(')','')
    lastSib = stepGroup.split(',')[-1].replace('q.v.','').strip()
    names = lastSib.split()
    if len(names)>1:
        return ' '.join(names[1:])
    else:
        return parentLast


def processDirectory(directoryPath):
    '''
    Create a list where each element is a dictionary
    representing the information of one directory entry
    Only include house number and family names
    '''
    with open(directoryPath,'r') as f:
        raw = f.read()

    members = []
    #Loop through raw lines and identify the first line after a gap
    #Use regex to ignore whitespace between lines
    for memberID,rawHouse in enumerate(re.split('\n[\t]*[ ]*\n',raw)):
        lines = rawHouse.split('\n')

        #Skip over empty lines
        for i,line in enumerate(lines):
            if len(line)==0:
                lines.pop(i)
        if len(lines)<3: #Ignoring 2-line redirects
            continue
        assert len(lines)>0

        #Split the name into proper name, nickname, and spouse
        member = parseHeadLine(lines[0],memberID)

        #Identify the lines after the phone numbers 
        #(###-####) and/or emails (xxx@xxx.xxx)
        firstChildLine = findFirstChildLine(lines)

        #Split the children on comma or semicolon
        if len(lines)>2 and (len(lines[firstChildLine:])>0):
            childString = ''.join(lines[firstChildLine:])
            member['children'] = parseChildString(childString,member)
        members.append(member)
    return members


def parseChildString(childString,member):
    stepGroups = childString.split(';')
    formattedChildren = []
    for stepGroup in stepGroups:
        last = getLastName(stepGroup,member['last'])
        children = stepGroup.split(',')
        for i,child in enumerate(children):
            if len(child)==0:
                continue
            formattedChild = {}
            #clean up garbled quotation characters
            child = child\
                .replace('\xe2\x80\x98','\'')\
                .replace('\xe2\x80\x99','\'')\
                .replace('\xe2\x80\x9c','\"')\
                .replace('\xe2\x80\x9d','\"')\
                .strip()
            # If parenthesized child got split, reunite
            if ('(' in child) and (')' not in child):
                child=(child + ',' + children[i+1]).strip()
                children.pop(i+1)

            #If child is a q.v. remove from name but mark it 'qv'
            if 'q.v' in child:
                child = child.replace('q.v.','').replace('q.v','').strip()
                formattedChild['qv']=True

            #if listed under husband's name:
            if ('(' in child) and (')' in child) and (',' in child):
                daughter,husband = child.replace(')','').split('(')
                formattedChild['last'] = husband.split(',',1)[0].strip()
                formattedChild['first'] = husband.split(',',1)[1].strip()
                formattedChild['daughter'] = daughter.strip()

            #if listed under own name:
            else:
                formattedChild['last'] = last.upper()
                formattedChild['first'] = child.split()[0]

            formattedChildren.append(formattedChild)
    return formattedChildren


def parseAdultChild(member):
    '''
    Parse adult child name for directory search terms.
    If adult child is otherwise listed under his own name,
    use child's last name and nickname as search terms
    If adult child is listed under spouse's name,
    use her spouse's last name and child's nickname as search terms
    '''
    #Loop through children's names
    if 'children' in member:
        for i,child in enumerate(member['children']):
            if 'qv' in child:  
                #find the child elsewhere in the directory,
                #then add id to children list
                member['children'][i]['id'] = searchDirectory(child, member['id'])


def searchDirectory(child, parentID):
    '''
    Search directory for listing of adult child under given name,
    or under husband's name.
    If found, return member ID
    '''
    global members
    last = child['last']
    first = child['first']
    if 'daughter' in child:
        daughter = child['daughter']
    else:
        daughter = None
    
    #define types of matches
    def lastNameMatch(member,last):
        return last.upper()==member['last'].upper()
    def firstNameMatch(member,first):
        return first.upper() in member['first'].upper()
    def nicknameMatch(member,first):
        return 'nickname' in member and first.upper() in member['nickname'].upper()
    def daughterMatch(member):
        return daughter and ('spouse' in member) and\
        daughter.upper() in member['spouse'].upper()
    def differentLastName(member,first):
        '''
        returns true if last name matches and either first name or nickname match
        '''
        foo = first.split()
        if len(foo)==2:
            first,last = foo
            return (lastNameMatch(member,last)) and\
             (firstNameMatch(member,first) or nicknameMatch(member,first))
        else:
            return False  
    def swapDaughter(member):
        '''
        If family is connected through daughter,
        maker daughter head of household
        '''
        if 'spouse' in member:
            first = member['spouse']
            member['spouse'] = member['last']+", "+member['first']
            member['first'] = first
    
    #search through members.
    #if last name matches and one of the first names matches, append
    for i,member in enumerate(members):
        if member['id'] != parentID and\
                ((lastNameMatch(member,last) and\
                (firstNameMatch(member,first) or nicknameMatch(member,first) or daughterMatch(member))) or\
                (not lastNameMatch(member,last) and differentLastName(member,first))):
            member['parentID'] = parentID
            
            #Switches for display purposes
            if daughterMatch(member):
                swapDaughter(member)
            elif not lastNameMatch(member,last):
                member['first'] = member['first']+' '+member['last'].title()
            return member['id']
    print "Not found: {}, {} ({})".format(last, first, daughter)

def alphabetize(members):
    return sorted(members, key=lambda k: k['last'])

def findMemberByID(ID):
    for member in members:
        if ID==member['id']:
            return member
        
def buildTree(member):
    '''
    Replace adult children with their own directory entry, 
    according to ID
    '''
    if 'children' in member:
        for i,child in enumerate(member['children']):
            if 'id' in child:
                child = findMemberByID(child['id'])
                buildTree(child)
                member['children'][i] = child
    return member


if __name__ == '__main__':
    #initialize global members
    members = processDirectory('data/directory2.txt')
    main(diagnostic=False)
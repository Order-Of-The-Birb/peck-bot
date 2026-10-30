import logging

logger = logging.getLogger(__name__)

def demarkdownify(text:str):
	replace_list = ["_", "*", "#", "~", "`", "|"]
	for i in replace_list:
		text = text.replace(i, "\\"+i)
	return text

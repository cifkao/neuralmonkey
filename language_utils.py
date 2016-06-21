# tests: mypy

import regex as re

try:
    #pylint: disable=unused-import,bare-except,import-error
    from typing import Dict
except:
    pass

def preprocess_char_based(sequence):
    return list(sequence)


def postprocess_char_based(sequences, _):
    return [["".join(sqc)] for sqc in sequences]


def untruecase(sentence):
    if sentence:
        return [sentence[0].capitalize()] + sentence[1:]
    else:
        return []

## Now starts the language specific code for geman

CONTRACTIONS = ["am", "ans", "beim", "im", "ins", "vom", "zum", "zur"]
CONTRACTIONS_SET = set(CONTRACTIONS)
UNCONTRACTED_FORMS = [["an", "dem"], ["an", "das"], ["bei", "dem"], ["in", "dem"],
                      ["in", "das"], ["von", "dem"], ["zu", "dem"], ["zu", "der"]]
UNCONTRACT = {c: un for c, un in zip(CONTRACTIONS, UNCONTRACTED_FORMS)}

CONTRACT = {} # type: Dict[str, Dict[str, str]]
for cont, (prep, article) in zip(CONTRACTIONS, UNCONTRACTED_FORMS):
    if not article in CONTRACT:
        CONTRACT[article] = {}
    CONTRACT[article][prep] = cont


EIN_TYPE_PRONOUNS = re.compile("^(ein|[mdsk]ein|ihr|unser|euer|Ihr)(e|es|er|em|en)$")
DER_TYPE_PRONOUNS = re.compile("^(dies|welch|jed|all)(e|es|er|em|en)$")

class GermanPreprocessor(object):
    def __init__(self, compounding=True, contracting=True, pronouns=True):
        self.compounding = compounding
        self.contracting = contracting
        self.pronouns = pronouns

    def __call__(self, sentence):
        result = []

        for word in sentence:
            if self.pronouns:
                ein_match = EIN_TYPE_PRONOUNS.match(word)
                der_match = DER_TYPE_PRONOUNS.match(word)

            if self.contracting and word in CONTRACTIONS_SET:
                result.extend(UNCONTRACT[word])
            elif self.pronouns and ein_match:
                result.append(ein_match[1])
                result.append("<<"+ein_match[2])
            elif self.pronouns and der_match:
                result.append(der_match[1])
                result.append("<<"+der_match[2])
            elif self.compounding and word.find(">><<") > -1:
                compound_parts = word.split(">><<")
                result.append(compound_parts[0])
                for wrd in compound_parts[1:]:
                    result.append(">><<")
                    result.append(wrd.capitalize())
            else:
                result.append(word)

        return result


class GermanPostprocessor(object):
    def __init__(self, compounding=True, contracting=True, pronouns=True):
        self.compounding = compounding
        self.contracting = contracting
        self.pronouns = pronouns

    def __call__(self, sentence):
        result = []

        compound = False
        for word in sentence:
            if self.contracting and word in CONTRACT \
                    and result and result[-1] in CONTRACT[word]:
                result[-1] = CONTRACT[word][result[-1]]
            elif self.pronouns and word.startswith("<<"):
                if result:
                    result[-1] += word[2:]
            elif self.compounding and result and word == ">><<":
                compound = True
            elif self.compounding and compound:
                result[-1] += word.lower()
                compound = False
            else:
                result.append(word)

        if result:
            result[0] = result[0].capitalize()

        return result

class SubPerformanceGrades:
    def __init__(self, thoughtGradeOptions=None, moralityOptions=None, abilityOptions=None,
                    knowledgeOptions=None, performanceOptions=None, postureOptions=None,
                    physicalOptions=None, hrSuggestionOptions=None):
            """
            :param thoughtGradeOptions: 思想評等
            :param moralityOptions: 品德評等
            :param abilityOptions: 能力評等
            :param knowledgeOptions: 知識評等
            :param performanceOptions: 表現評等
            :param postureOptions: 體態評等
            :param physicalOptions: 體能評等
            :param hrSuggestionOptions: 人資建議
            """
            self.thoughtGradeOptions = thoughtGradeOptions
            self.moralityOptions = moralityOptions
            self.abilityOptions = abilityOptions
            self.knowledgeOptions = knowledgeOptions
            self.performanceOptions = performanceOptions
            self.postureOptions = postureOptions
            self.physicalOptions = physicalOptions
            self.hrSuggestionOptions = hrSuggestionOptions

    def __repr__(self):
        return (f"<Evaluation thoughtGradeOptions={self.thoughtGradeOptions}, "
                f"moralityOptions={self.moralityOptions}, abilityOptions={self.abilityOptions}, "
                f"knowledgeOptions={self.knowledgeOptions}, performanceOptions={self.performanceOptions}, "
                f"postureOptions={self.postureOptions}, physicalOptions={self.physicalOptions}, "
                f"hrSuggestionOptions={self.hrSuggestionOptions}>")
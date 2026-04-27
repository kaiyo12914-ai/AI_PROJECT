from webapps.llm.llm_factory import get_chat_model

def test_lm_studio_modelType():
    llm = get_chat_model(0.7,30,"LM_STUDIO")
    output = llm.invoke("請用50個字進行自我介紹，並告訴我你的名字")
    print(output)
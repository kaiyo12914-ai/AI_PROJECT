from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_community.chains.llm_requests import LLMRequestsChain

# Initialize the Ollama model
model_name = "mistral_small_3_1_2503:latest"  # or another available model like "mistral"
llm = Ollama(model=model_name,base_url="http://mpcai.mpc.mil.tw:11434")
result = llm.invoke("Hello")

print(result)

# Create a prompt template for question answering
template = """Question: {question}

Answer: Let's work this out in a step by step manner to be sure we have the right answer.

1. First, I will rephrase the question to ensure I understand it correctly.
   Rephrased question:
   {rephrased_question}

2. Next, I will break down the question into smaller parts to tackle each aspect separately.
   Broken down questions:
   - Part 1: {part_1}
   - Part 2: {part_2}

3. Then, I will think through potential answers for each part.

4. Finally, I will combine all the information and provide a concise answer.

Answer:"""

# prompt = ChatPromptTemplate(
#     input_variables=["question", "rephrased_question", "part_1", "part_2"],
#     template=template,
# )

# prompt = ChatPromptTemplate.from_messages([
#         ("system", "你是專業助理，請依據提供的資料回答；若資料不足請明確說明資料不足。"),
#         ("user", "資料如下：\n{context}\n\n問題：{question}")
#     ]).format_messages(context=context, question=question)

# Create an LLMChain
chain = LLMRequestsChain(llm=ollama, prompt="Hello")

# Example usage
question = "What is the capital of France?"
rephrased_question = "Which city serves as the capital of the country known as France?"
part_1 = "What do we know about France as a country?"
part_2 = "Where are capitals typically located and why?"

result = chain.run()

print("Answer:", result)
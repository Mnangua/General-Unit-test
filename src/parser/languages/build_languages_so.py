from tree_sitter import Language  
  
Language.build_library(  
  # 生成的 so 路径  
  'build/my-languages.so',  
  [  
    'tree-sitter-python',  
    'tree-sitter-java'  
  ]  
)  
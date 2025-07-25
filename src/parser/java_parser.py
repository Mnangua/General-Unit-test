import os
import sys
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum

import tree_sitter_java
from tree_sitter import Language, Parser

class CallableType(Enum):
    PUBLIC_CLASS = "public_class"
    PUBLIC_INTERFACE = "public_interface"
    PUBLIC_ENUM = "public_enum"
    PUBLIC_ANNOTATION = "public_annotation"
    PUBLIC_METHOD = "public_method"
    PUBLIC_CONSTRUCTOR = "public_constructor"
    PUBLIC_FIELD = "public_field"
    STATIC_METHOD = "static_method"
    STATIC_FIELD = "static_field"
    PACKAGE_PRIVATE_CLASS = "package_private_class"
    PACKAGE_PRIVATE_METHOD = "package_private_method"
    PACKAGE_PRIVATE_FIELD = "package_private_field"
    PROTECTED_METHOD = "protected_method"
    PROTECTED_FIELD = "protected_field"
    PUBLIC_CONSTANT = "public_constant"
    STATIC_CONSTANT = "static_constant"

@dataclass
class CallableElement:
    """Represents a callable Java code element"""
    name: str
    callable_type: CallableType
    code: str
    signature: str
    modifiers: List[str]
    line_start: int
    line_end: int
    package_name: Optional[str] = None
    class_name: Optional[str] = None
    return_type: Optional[str] = None
    parameters: List[str] = None

class JavaCallableExtractor:
    """Java code callable element extractor"""
    
    def __init__(self):
        self.language = Language(tree_sitter_java.language())
        self.parser = Parser(self.language)
        self.code = ""
        self.code_bytes = b""
        
    def extract_all_callable_elements(self, java_code: str) -> List[CallableElement]:
        """
        Extract all elements in Java code that can be called by other code
        
        Args:
            java_code: Complete Java source code string
            
        Returns:
            List containing all callable elements
        """
        self.code = java_code
        self.code_bytes = java_code.encode('utf-8')
        tree = self.parser.parse(self.code_bytes)
        root_node = tree.root_node
        
        callable_elements = []
        
        # Get package name
        package_name = self._get_package_name(root_node)
        
        # Extract class-level callable elements
        callable_elements.extend(self._extract_type_declarations(root_node, package_name))
        
        # Extract methods and fields
        callable_elements.extend(self._extract_methods_and_fields(root_node, package_name))
        
        return callable_elements
    
    def _get_package_name(self, root_node) -> Optional[str]:
        """Extract package name"""
        package_nodes = self._find_nodes_by_type(root_node, "package_declaration")
        if package_nodes:
            package_node = package_nodes[0]
            # Find scoped_identifier or identifier
            identifiers = self._find_nodes_by_type(package_node, ["scoped_identifier", "identifier"])
            if identifiers:
                return self._get_node_text(identifiers[0])
        return None
    
    def _extract_type_declarations(self, root_node, package_name: Optional[str]) -> List[CallableElement]:
        """Extract class, interface, enum, annotation declarations"""
        elements = []
        
        # Find all type declarations
        type_nodes = self._find_nodes_by_type(root_node, [
            "class_declaration", 
            "interface_declaration", 
            "enum_declaration",
            "annotation_type_declaration"
        ])
        
        for node in type_nodes:
            element = self._extract_type_declaration(node, package_name)
            if element:
                elements.append(element)
                
        return elements
    
    def _extract_type_declaration(self, node, package_name: Optional[str]) -> Optional[CallableElement]:
        """Extract single type declaration"""
        modifiers = self._get_modifiers(node)
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
            
        name = self._get_node_text(name_node)
        code = self._get_node_text(node)
        
        # Determine type
        if node.type == "class_declaration":
            callable_type = CallableType.PUBLIC_CLASS if "public" in modifiers else CallableType.PACKAGE_PRIVATE_CLASS
        elif node.type == "interface_declaration":
            callable_type = CallableType.PUBLIC_INTERFACE
        elif node.type == "enum_declaration":
            callable_type = CallableType.PUBLIC_ENUM
        elif node.type == "annotation_type_declaration":
            callable_type = CallableType.PUBLIC_ANNOTATION
        else:
            return None
            
        # Build signature
        modifier_str = ' '.join(modifiers) if modifiers else ''
        type_name = node.type.replace('_declaration', '')
        signature = f"{modifier_str} {type_name} {name}".strip()
        
        return CallableElement(
            name=name,
            callable_type=callable_type,
            code=code,
            signature=signature,
            modifiers=modifiers,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            package_name=package_name,
            class_name=name
        )
    
    def _extract_methods_and_fields(self, root_node, package_name: Optional[str]) -> List[CallableElement]:
        """Extract methods and fields"""
        elements = []
        
        # Find all classes and interfaces
        type_nodes = self._find_nodes_by_type(root_node, [
            "class_declaration", 
            "interface_declaration", 
            "enum_declaration"
        ])
        
        for type_node in type_nodes:
            class_name = None
            name_node = type_node.child_by_field_name("name")
            if name_node:
                class_name = self._get_node_text(name_node)
            
            # Extract methods
            method_nodes = self._find_nodes_by_type(type_node, [
                "method_declaration", 
                "constructor_declaration"
            ])
            
            for method_node in method_nodes:
                element = self._extract_method(method_node, package_name, class_name)
                if element:
                    elements.append(element)
            
            # Extract fields
            field_nodes = self._find_nodes_by_type(type_node, "field_declaration")
            for field_node in field_nodes:
                field_elements = self._extract_fields(field_node, package_name, class_name)
                elements.extend(field_elements)
                
        return elements
    
    def _extract_method(self, node, package_name: Optional[str], class_name: Optional[str]) -> Optional[CallableElement]:
        """Extract method declaration"""
        modifiers = self._get_modifiers(node)
        
        # Skip private methods
        if "private" in modifiers:
            return None
            
        # Get method name
        name_node = node.child_by_field_name("name")
        if not name_node and node.type == "constructor_declaration":
            # Constructor uses class name
            name = class_name or "constructor"
        elif name_node:
            name = self._get_node_text(name_node)
        else:
            return None
        
        # Get return type
        return_type = None
        type_node = node.child_by_field_name("type")
        if type_node:
            return_type = self._get_node_text(type_node)
        
        # Get parameters
        parameters = self._extract_parameters(node)
        
        # Determine method type
        if node.type == "constructor_declaration":
            if "public" in modifiers:
                callable_type = CallableType.PUBLIC_CONSTRUCTOR
            else:
                callable_type = CallableType.PACKAGE_PRIVATE_METHOD
        elif "static" in modifiers:
            callable_type = CallableType.STATIC_METHOD
        elif "public" in modifiers:
            callable_type = CallableType.PUBLIC_METHOD
        elif "protected" in modifiers:
            callable_type = CallableType.PROTECTED_METHOD
        else:
            callable_type = CallableType.PACKAGE_PRIVATE_METHOD
        
        # Build signature
        modifier_str = ' '.join(modifiers) if modifiers else ''
        param_str = ", ".join(parameters) if parameters else ""
        
        if node.type == "constructor_declaration":
            signature = f"{modifier_str} {name}({param_str})".strip()
        else:
            return_type_str = return_type or 'void'
            signature = f"{modifier_str} {return_type_str} {name}({param_str})".strip()
        
        code = self._get_node_text(node)
        
        return CallableElement(
            name=name,
            callable_type=callable_type,
            code=code,
            signature=signature,
            modifiers=modifiers,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            package_name=package_name,
            class_name=class_name,
            return_type=return_type,
            parameters=parameters
        )
    
    def _extract_fields(self, node, package_name: Optional[str], class_name: Optional[str]) -> List[CallableElement]:
        """Extract field declarations (one field declaration may contain multiple variables)"""
        elements = []
        modifiers = self._get_modifiers(node)
        
        # Skip private fields
        if "private" in modifiers:
            return elements
        
        # Get field type
        type_node = node.child_by_field_name("type")
        field_type = self._get_node_text(type_node) if type_node else "unknown"
        
        # Find all variable declarations
        variable_nodes = self._find_nodes_by_type(node, "variable_declarator")
        
        for var_node in variable_nodes:
            name_node = var_node.child_by_field_name("name")
            if not name_node:
                continue
                
            name = self._get_node_text(name_node)
            
            # Check if it's a constant (final static)
            is_constant = "final" in modifiers and "static" in modifiers
            
            # Determine field type
            if is_constant:
                if "public" in modifiers:
                    callable_type = CallableType.PUBLIC_CONSTANT
                else:
                    callable_type = CallableType.STATIC_CONSTANT
            elif "static" in modifiers:
                callable_type = CallableType.STATIC_FIELD
            elif "public" in modifiers:
                callable_type = CallableType.PUBLIC_FIELD
            elif "protected" in modifiers:
                callable_type = CallableType.PROTECTED_FIELD
            else:
                callable_type = CallableType.PACKAGE_PRIVATE_FIELD
            
            # Build signature
            modifier_str = ' '.join(modifiers) if modifiers else ''
            signature = f"{modifier_str} {field_type} {name}".strip()
            
            # Get complete field declaration code
            code = self._get_node_text(node)
            
            elements.append(CallableElement(
                name=name,
                callable_type=callable_type,
                code=code,
                signature=signature,
                modifiers=modifiers,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                package_name=package_name,
                class_name=class_name,
                return_type=field_type
            ))
            
        return elements
    
    def _extract_parameters(self, method_node) -> List[str]:
        """Extract method parameters"""
        parameters = []
        param_list_node = method_node.child_by_field_name("parameters")
        
        if param_list_node:
            param_nodes = self._find_nodes_by_type(param_list_node, "formal_parameter")
            for param_node in param_nodes:
                type_node = param_node.child_by_field_name("type")
                name_node = param_node.child_by_field_name("name")
                
                if type_node and name_node:
                    param_type = self._get_node_text(type_node)
                    param_name = self._get_node_text(name_node)
                    parameters.append(f"{param_type} {param_name}")
                    
        return parameters
    
    def _get_modifiers(self, node) -> List[str]:
        """Extract node's direct modifiers (fixed version)"""
        modifiers = []
        
        # Only find modifiers in direct child nodes of current node
        for child in node.children:
            if child.type == "modifiers":
                # Iterate through direct child nodes of modifiers node
                for modifier_child in child.children:
                    if modifier_child.type in [
                        "public", "private", "protected", "static", "final", 
                        "abstract", "synchronized", "native", "strictfp", 
                        "transient", "volatile"
                    ]:
                        modifiers.append(modifier_child.type)
                break  # Exit after finding the first modifiers node
                    
        return modifiers
    
    def _find_nodes_by_type(self, root_node, node_types) -> List:
        """Find all nodes of specified types"""
        if isinstance(node_types, str):
            node_types = [node_types]
            
        result = []
        
        def traverse(node):
            if node.type in node_types:
                result.append(node)
            for child in node.children:
                traverse(child)
        
        traverse(root_node)
        return result
    
    def _get_node_text(self, node) -> str:
        """Get text corresponding to node"""
        return self.code_bytes[node.start_byte:node.end_byte].decode('utf-8')
    
    def group_by_type(self, elements: List[CallableElement]) -> Dict[CallableType, List[CallableElement]]:
        """Group callable elements by type"""
        grouped = {}
        for element in elements:
            if element.callable_type not in grouped:
                grouped[element.callable_type] = []
            grouped[element.callable_type].append(element)
        return grouped
    
    def filter_public_only(self, elements: List[CallableElement]) -> List[CallableElement]:
        """Keep only public callable elements"""
        public_types = {
            CallableType.PUBLIC_CLASS,
            CallableType.PUBLIC_INTERFACE,
            CallableType.PUBLIC_ENUM,
            CallableType.PUBLIC_ANNOTATION,
            CallableType.PUBLIC_METHOD,
            CallableType.PUBLIC_CONSTRUCTOR,
            CallableType.PUBLIC_FIELD,
            CallableType.PUBLIC_CONSTANT
        }
        return [elem for elem in elements if elem.callable_type in public_types]
    
    def filter_static_only(self, elements: List[CallableElement]) -> List[CallableElement]:
        """Keep only static callable elements"""
        static_types = {
            CallableType.STATIC_METHOD,
            CallableType.STATIC_FIELD,
            CallableType.STATIC_CONSTANT
        }
        return [elem for elem in elements if elem.callable_type in static_types or "static" in elem.modifiers]

def main():
    """Example usage"""
    
    # Sample Java code
    sample_java_code = """
package com.example.demo;

import java.util.List;
import java.util.ArrayList;

/**
 * Example class for demonstrating callable element extraction
 */
public class DemoService {
    
    public static final String VERSION = "1.0.0";
    private static final int MAX_SIZE = 100;
    
    public String name;
    protected int count;
    private String secret;
    
    public DemoService() {
        this.name = "Demo";
    }
    
    public DemoService(String name) {
        this.name = name;
    }
    
    public static void staticMethod() {
        System.out.println("Static method");
    }
    
    public String getName() {
        return name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
    
    protected void protectedMethod() {
        // Protected method
    }
    
    private void privateMethod() {
        // Private method - should not be extracted
    }
    
    public List<String> getItems(int limit) {
        List<String> items = new ArrayList<>();
        for (int i = 0; i < limit && i < MAX_SIZE; i++) {
            items.add("Item " + i);
        }
        return items;
    }
}

interface PublicInterface {
    void interfaceMethod();
    
    default void defaultMethod() {
        System.out.println("Default method");
    }
}

enum Status {
    ACTIVE, INACTIVE, PENDING
}

class PackagePrivateClass {
    void packageMethod() {
        // Package private method
    }
}
"""
    
    # Create extractor and extract callable elements
    extractor = JavaCallableExtractor()
    callable_elements = extractor.extract_all_callable_elements(sample_java_code)
    
    print(f"Extracted {len(callable_elements)} callable elements:\n")
    
    # Display grouped by type
    grouped = extractor.group_by_type(callable_elements)
    
    for callable_type, elements in grouped.items():
        print(f"\n=== {callable_type.value.upper()} ===")
        for element in elements:
            print(f"Name: {element.name}")
            print(f"Signature: {element.signature}")
            print(f"Lines: {element.line_start}-{element.line_end}")
            if element.package_name:
                print(f"Package: {element.package_name}")
            if element.class_name:
                print(f"Class: {element.class_name}")
            print(f"Modifiers: {element.modifiers}")
            print("Code:")
            print(element.code[:200] + "..." if len(element.code) > 200 else element.code)
            print("-" * 50)
    
    # Show only public elements
    print("\n\n=== Show only public callable elements ===")
    public_elements = extractor.filter_public_only(callable_elements)
    for element in public_elements:
        print(f"{element.callable_type.value}: {element.signature}")
    
    # Show only static elements
    print("\n\n=== Show only static callable elements ===")
    static_elements = extractor.filter_static_only(callable_elements)
    for element in static_elements:
        print(f"{element.callable_type.value}: {element.signature}")

if __name__ == "__main__":
    main()
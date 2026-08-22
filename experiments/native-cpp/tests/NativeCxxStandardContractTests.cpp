#include <iostream>

#ifndef TB_REQUESTED_CXX_STANDARD
#error "TB_REQUESTED_CXX_STANDARD must be supplied by the CMake project."
#endif

#if TB_REQUESTED_CXX_STANDARD != 23 && TB_REQUESTED_CXX_STANDARD != 26
#error "The native build supports only C++23 and the optional C++26 mode."
#endif

#if TB_REQUESTED_CXX_STANDARD == 26
#if defined(_MSC_VER)
#if !defined(_MSVC_LANG) || _MSVC_LANG < 202302L
#error "The MSVC C++26 opt-in did not select a current working-draft language mode."
#endif
#elif defined(__clang__) || defined(__GNUC__)
#if !defined(__cplusplus) || __cplusplus < 202400L
#error "The GNU/Clang C++26 opt-in did not select a C++26 preview language mode."
#endif
#else
#error "The C++26 contract test needs a recognized compiler language-mode macro."
#endif
#endif

int main()
{
    std::cout << "requested_cxx_standard=C++" << TB_REQUESTED_CXX_STANDARD << '\n';
#if defined(_MSVC_LANG)
    std::cout << "compiler_language_macro=_MSVC_LANG:" << _MSVC_LANG << '\n';
#elif defined(__cplusplus)
    std::cout << "compiler_language_macro=__cplusplus:" << __cplusplus << '\n';
#endif
    return 0;
}

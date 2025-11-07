
/**
    Used to be a python script (See old_compress_translations.py)
    But then I found out python doesn't ship with modern macOS anymore, so now it's an objc script.

    Test using this command:
        `clang mac-mouse-fix-scripts/scripts/uploadstrings/compress_translations/compress_translations.m -fmodules -g -o <executable_path>; <executable_path>;`
        - You probably want the executable_path to point right into an existing `Compress xcloc files.app` surrounded by .xcloc files that it can compress, since the script expects to be ran like that. 
        - -g in case you wanna attach debugger
    
    Release using instructions in `UploadStringsReadme.md`

*/

#import <Foundation/Foundation.h>
#import <Cocoa/Cocoa.h>

#include <stdio.h>
#include <unistd.h>

#define auto __auto_type
#define stringf(fmt, args...)   [NSString stringWithFormat: @"" fmt, ## args]
#define strip(str)              [(str) stringByTrimmingCharactersInSet: [NSCharacterSet whitespaceAndNewlineCharacterSet]]
#define replace(str, searched, replacement) [(str) stringByReplacingOccurrencesOfString: (searched) withString: (replacement) options: 0 range: NSMakeRange(0, str.length)]

#define cwd()           [[NSFileManager defaultManager] currentDirectoryPath]
#define cd(path)        [[NSFileManager defaultManager] changeCurrentDirectoryPath: (path)]

#define log(fmt, args...) printf("%s\n", stringf(@"" fmt, ## args).UTF8String)

void show_alert(NSString *message) {
    #define show_alert(fmt, args...) show_alert(stringf(fmt, ## args))

    // Showing alert for user-feedback since stdout is not visible when launching the script by double-clicking the enclosing app-bundle [Oct 2025]
    // Use osascript to display alert cause that's the only way to avoid the app icon. And we've already designed the alert text around that look when originally writing this program in Python. CFUserNotificationDisplayNotice() also has the NSAlert look [Oct 2025]
    //      Caution: If msg contains double-quote (") or escaped single-quote (\') here it breaks the osascript. Not sure why. [Oct 2025]

    auto src = stringf(@"display dialog \"%@\" with title \"\" buttons {\"OK\"} default button 1", replace(strip(message), @"\"", @"\\\""));
    auto script = [[NSAppleScript alloc] initWithSource: src];
    
    NSDictionary *err = nil;
    [script executeAndReturnError: &err];
    
    if (err) log("osascript failed with error: %@.\nsrc:\n%@", err, src); // Seems to fail when you run the executable directly, without being embedded in an .app bundle.
    
    log("show_alert invoked with: %@", message); // Log as a backup in case osascript silently fails
}

NSString *runclt(NSString *command) {

    if ((0)) log("runclt invoked with: %@", command);

    auto pipe = [NSPipe new];
    auto error_pipe = [NSPipe new];

    auto task = [NSTask new];
    task.launchPath = @"/bin/zsh"; // bash doesn't support recursive globbing by default, so we're using zsh
    task.arguments = @[@"-c", command];
    task.standardOutput = pipe;
    task.standardError = error_pipe;
    [task launch];
    [task waitUntilExit];
    
    auto stdout = strip([[NSString alloc] initWithData: [[pipe       fileHandleForReading] readDataToEndOfFile] encoding: NSUTF8StringEncoding]);
    auto stderr = strip([[NSString alloc] initWithData: [[error_pipe fileHandleForReading] readDataToEndOfFile] encoding: NSUTF8StringEncoding]);

    if (stderr.length) log("command '%@' was run with cwd %@ and returned error: %@", command, cwd(), stderr);

    return stdout;
}
#define mfglob(pattern) ({ \
    auto r = runclt(@"printf \"%s\n\" " pattern); /* If filenames contain \n, this could break, but doesn't produce hacker vunerabilities I think [Oct 2025]*/\
    [r isEqual: @""] ? @[] : [r componentsSeparatedByString: @"\n"]; \
})

NSString *paths_to_shell_args(NSArray<NSString *> *path_array) { /* Turn array of paths to single string that can be passed as shell args. */
    auto result = [NSMutableString new]; 
    for (int i = 0; i < path_array.count; i++) { 
        if (i) [result appendString: @" "];
        [result appendFormat: @"'%@'", replace(path_array[i], @"'", @"\\'")]; // Sorta like shlex.quote(). replacing `'` to guard against HACKERS who wanna ship this executable next to .xloc files with malicious names. (They could include zsh commands) (This is what translocation is supposed to guard against.) [Oct 2025]
    } 
    return result;
}

NSNumber *get_checksum(NSString *file_path) {
    int result = 0;
    auto data = [NSData dataWithContentsOfFile: file_path];
    const char *bytes = data.bytes; // Unpack, otherwise objc_msgSend takes up a lot of time
    int len = data.length;
    for (int i = 0; i < len; i++) result -= bytes[i];
    return @(result);
}

int main(int argc, char *argv[]) {

    #define fail(x...) { show_alert(x); exit(1); }

    // Undo App Translocation, so we can access the .xcloc files next to the .app bundle
    //      (Also see AppTranslocationManager.m from Mac Mouse Fix)
    auto script_path = @(argv[0]);
    auto app_url = [[NSURL fileURLWithPath: stringf("%@%@", script_path, @"/../../..")] standardizedURL]; /// Get the app bundle path (we're in Contents/MacOS)
    {
        NSURL *original_url = nil;
        {
            extern CFURLRef SecTranslocateCreateOriginalPathForURL(CFURLRef translocatedPath, CFErrorRef *error);
            CFErrorRef err = NULL;
            original_url = CFBridgingRelease(SecTranslocateCreateOriginalPathForURL((__bridge void *)app_url, &err));
            if (err) fail("Error while removing app translocation: %@", err); // Failing to prevent infinite loop in case we can't remove quarantine for some reason. [Oct 2025]
        }

        if ([app_url isEqual: original_url]) 
            log(@"App doesn't seem to be translocated at path %@. Proceeding...", app_url.path);
        else {
            log(@"App seems to be translocated ('%@' -> '%@'). Removing quarantine and relaunching....", app_url.path, original_url.path);

            runclt(stringf("xattr -cr '%@'", original_url.path));
            runclt(stringf("open -n '%@'", original_url.path));
            exit(0);
        }
    }

    // Change working dir to the parent of the .app – That's where the .xcloc files are.
    cd([app_url.path stringByDeletingLastPathComponent]);
    
    // Deduplicate .jpeg files using hardlinks
    NSMutableDictionary<NSNumber *, NSString *> *seen = [NSMutableDictionary new];
    for (NSString *file in mfglob(@"**/*.jpeg")) {
        
        // Vibecoded python script ran `if not file.is_file(): continue` here – not sure why [Oct 2025]
        auto checksum = get_checksum(file);
        if (!seen[checksum]) seen[checksum] = file;
        else {
            auto original_file = seen[checksum];
            unlink(file.UTF8String);
            link(original_file.UTF8String, file.UTF8String); // Using C functions cause runclt actually slows down things a lot in this tight loop.
        }
    }

    // Find xcloc files
    auto xcloc_files = mfglob(@"*.xcloc");
    if (!xcloc_files.count) fail("Error: Found no .xcloc files in folder:\n'%@'", cwd());

    // Define (localizer facing) archive name
    auto archive_name = @"Compressed Translations (Upload This).tar.gz"; // Note how we're calling them 'xcloc files' before archiving and 'translations' after. Not sure this makes sense, but I like it. translation_guide.md also uses both terms [Oct 2025]

    // Compress .xcloc files using tar (zip doesn't preserve the hardlink deduplication)
    runclt(stringf("tar -czf '%@' %@", archive_name, paths_to_shell_args(xcloc_files)));

    // Show success message
    show_alert(@""
        "\n🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁"
        "\n"
        "\nCreated file:"
        "\n%@"
        "\n"
        "\nYou can upload the compressed translations via:"
        "\n"
        "\nGitHub: "
        "\nhttps://redirect.macmousefix.com/?target=mmf-localization-contribution"
        "\n"
        "\nEmail:"
        "\nhttps://redirect.macmousefix.com/?target=mailto-noah"
        "\n"
        "\n🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁🌐🐁"
    , archive_name);

    // Exit success
    return 0;
}
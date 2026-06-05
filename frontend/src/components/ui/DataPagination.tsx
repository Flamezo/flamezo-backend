import * as React from "react"
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  MoreHorizontal,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

interface DataPaginationProps {
  currentPage: number
  totalCount: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
  isLoading?: boolean
  className?: string
}

export function DataPagination({
  currentPage,
  totalCount,
  pageSize,
  onPageChange,
  onPageSizeChange,
  isLoading = false,
  className,
}: DataPaginationProps) {
  const totalPages = Math.ceil(totalCount / pageSize) || 1
  const startEntry = (currentPage - 1) * pageSize + 1
  const endEntry = Math.min(currentPage * pageSize, totalCount)

  // Generate page numbers to show
  const getPageNumbers = () => {
    const pages: (number | string)[] = []
    const delta = 1 // Number of pages either side of current

    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pages.push(i)
    } else {
      pages.push(1)
      if (currentPage > delta + 2) pages.push("...")
      
      const start = Math.max(2, currentPage - delta)
      const end = Math.min(totalPages - 1, currentPage + delta)
      
      for (let i = start; i <= end; i++) pages.push(i)
      
      if (currentPage < totalPages - delta - 1) pages.push("...")
      pages.push(totalPages)
    }
    return pages
  }

  return (
    <div className={cn("flex items-center justify-between flex-wrap gap-4 py-4 px-2 select-none", className)}>
      {/* Left side: Range stats */}
      <div className="flex-1 text-sm text-muted-foreground whitespace-nowrap">
        {isLoading ? (
          <span className="animate-pulse">Loading items...</span>
        ) : (
          <>
            Showing <span className="font-semibold text-foreground">{totalCount === 0 ? 0 : startEntry}</span> to{" "}
            <span className="font-semibold text-foreground">{endEntry}</span> of{" "}
            <span className="font-semibold text-foreground">{totalCount}</span> entries
          </>
        )}
      </div>

      <div className="flex items-center space-x-6 lg:space-x-8">
        {/* Page Size Selector */}
        <div className="flex items-center space-x-2">
          <p className="text-sm font-medium">Rows per page</p>
          <Select
            value={`${pageSize}`}
            onValueChange={(value) => {
              onPageSizeChange(Number(value))
            }}
          >
            <SelectTrigger className="h-8 w-[70px]">
              <SelectValue placeholder={pageSize} />
            </SelectTrigger>
            <SelectContent side="top">
              {[10, 20, 50, 100, 200, 500].map((size) => (
                <SelectItem key={size} value={`${size}`}>
                  {size}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Page Navigation */}
        <div className="flex items-center space-x-2">
          <div className="flex w-[100px] items-center justify-center text-sm font-medium">
            Page {currentPage} of {totalPages}
          </div>
          <div className="flex items-center space-x-1">
            <Button
              variant="outline"
              className="hidden h-8 w-8 p-0 lg:flex"
              onClick={() => onPageChange(1)}
              disabled={currentPage === 1 || isLoading}
            >
              <span className="sr-only">Go to first page</span>
              <ChevronsLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              className="h-8 w-8 p-0"
              onClick={() => onPageChange(currentPage - 1)}
              disabled={currentPage === 1 || isLoading}
            >
              <span className="sr-only">Go to previous page</span>
              <ChevronLeft className="h-4 w-4" />
            </Button>

            {/* Render numbered buttons for desktop if pages are few */}
            <div className="hidden sm:flex items-center space-x-1 mx-2">
               {getPageNumbers().map((page, index) => (
                 <React.Fragment key={index}>
                    {page === "..." ? (
                      <span className="px-2 text-muted-foreground"><MoreHorizontal className="h-4 w-4" /></span>
                    ) : (
                      <Button
                        variant={currentPage === page ? "default" : "ghost"}
                        className={cn(
                          "h-8 w-8 p-0 text-xs",
                          currentPage === page ? "pointer-events-none" : ""
                        )}
                        onClick={() => onPageChange(page as number)}
                        disabled={isLoading}
                      >
                        {page}
                      </Button>
                    )}
                 </React.Fragment>
               ))}
            </div>

            <Button
              variant="outline"
              className="h-8 w-8 p-0"
              onClick={() => onPageChange(currentPage + 1)}
              disabled={currentPage === totalPages || isLoading}
            >
              <span className="sr-only">Go to next page</span>
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              className="hidden h-8 w-8 p-0 lg:flex"
              onClick={() => onPageChange(totalPages)}
              disabled={currentPage === totalPages || isLoading}
            >
              <span className="sr-only">Go to last page</span>
              <ChevronsRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
